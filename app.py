import requests
import json
import pandas as pd
import time
import re
import io # Used for in-memory file handling
from flask import Flask, request, send_file, jsonify
from groq import Groq
from trafilatura import fetch_url, extract
from bs4 import BeautifulSoup
from urllib.parse import urlparse, parse_qs
from youtube_comment_downloader import YoutubeCommentDownloader
from youtube_transcript_api import YouTubeTranscriptApi
from fake_useragent import UserAgent

app = Flask(__name__)

# ==========================================
# YOUR LOGIC CLASS (ADAPTED FOR WEB)
# ==========================================
class SEOIntelligenceHub:
    def __init__(self, serper_key, groq_key):
        self.headers = {'X-API-KEY': serper_key, 'Content-Type': 'application/json'}
        self.groq_key = groq_key.strip()
        self.yt_downloader = YoutubeCommentDownloader()
        self.ua = UserAgent()
        
        if self.groq_key and "gsk_" in self.groq_key:
            try:
                self.groq_client = Groq(api_key=self.groq_key)
                self.use_ai = True
            except: 
                self.use_ai = False
        else: 
            self.use_ai = False

    def get_competitors(self, keyword):
        url = "https://google.serper.dev/search"
        payload = json.dumps({"q": keyword, "num": 10})
        try:
            response = requests.post(url, headers=self.headers, data=payload)
            results = response.json().get("organic", [])
            valid = []
            for res in results:
                link = res.get("link", "")
                if "reddit" not in link and "youtube" not in link and "quora" not in link:
                    valid.append(link)
                if len(valid) == 4: break
            return valid
        except: return []

    def extract_page_data(self, url):
        data = {"URL": url, "Status": "Failed", "Meta Title": "N/A", "Meta Description": "N/A", "Headings (H1-H3)": "N/A", "FAQ Schema": "No", "Word Count": 0}
        try:
            downloaded = fetch_url(url)
            if not downloaded: return data
            main_text = extract(downloaded)
            data["Word Count"] = len(main_text.split()) if main_text else 0
            soup = BeautifulSoup(downloaded, 'html.parser')
            data["Meta Title"] = soup.title.string.strip() if soup.title else "N/A"
            meta_desc = soup.find("meta", attrs={"name": "description"})
            if meta_desc: data["Meta Description"] = meta_desc.get("content", "N/A")
            headings_list = []
            for i in range(1, 4):
                tags = soup.find_all(f'h{i}')
                if tags:
                    texts = " | ".join([t.get_text(strip=True)[:80] for t in tags[:3]]) 
                    headings_list.append(f"[H{i}]: {texts}")
            data["Headings (H1-H3)"] = "\n".join(headings_list)
            if "FAQPage" in str(soup) or "faq" in url.lower(): data["FAQ Schema"] = "YES"
            data["Status"] = "Success"
            return data
        except: return data

    def get_community_questions(self, keyword):
        data = []
        platforms = [("Reddit", "site:reddit.com"), ("Quora", "site:quora.com")]
        for platform_name, site_operator in platforms:
            payload = json.dumps({"q": f"{site_operator} {keyword}", "num": 5})
            try:
                resp = requests.post("https://google.serper.dev/search", headers=self.headers, data=payload)
                for res in resp.json().get("organic", []):
                    data.append({
                        "Keyword": keyword,
                        "Platform": platform_name,
                        "Question": res.get("title"),
                        "Link": res.get("link")
                    })
            except: pass
        return data

    def get_video_id(self, url):
        parsed = urlparse(url)
        if parsed.hostname == 'youtu.be': return parsed.path[1:]
        if parsed.hostname in ('www.youtube.com', 'youtube.com'):
            if parsed.path == '/watch': return parse_qs(parsed.query)['v'][0]
        return None

    def analyze_transcript(self, text, source_type="Transcript"):
        if not self.use_ai: return "AI Not Active"
        sys_prompt = "You are an SEO Expert. Extract 3 actionable technical SEO tips from this video content. Keep it brief."
        try:
            completion = self.groq_client.chat.completions.create(
                messages=[{"role":"system","content": sys_prompt},{"role":"user","content":text[:15000]}],
                model="llama-3.1-8b-instant", temperature=0.5, max_tokens=300
            )
            return completion.choices[0].message.content
        except: return "AI Error"

    def get_youtube_strategy(self, keyword):
        video_data = []
        payload = json.dumps({"q": f"site:youtube.com {keyword}", "num": 10})
        try:
            resp = requests.post("https://google.serper.dev/search", headers=self.headers, data=payload)
            valid_videos = []
            for res in resp.json().get("organic", []):
                if "watch?v=" in res.get("link", "") and "shorts" not in res.get("link", ""):
                    valid_videos.append(res)
                if len(valid_videos) == 3: break
            
            for vid in valid_videos:
                link = vid.get("link")
                vid_id = self.get_video_id(link)
                title = vid.get("title").replace(" - YouTube", "")
                snippet = vid.get("snippet", "")
                final_text = ""
                source_used = ""
                try:
                    ts = YouTubeTranscriptApi.get_transcript(vid_id, languages=['en', 'en-US', 'auto'])
                    final_text = " ".join([t['text'] for t in ts])
                    source_used = "Transcript"
                except: 
                    final_text = snippet
                    source_used = "Snippet"
                
                if final_text: analysis = self.analyze_transcript(final_text, source_used)
                else: analysis = "No Data Available"
                
                video_data.append({
                    "Keyword": keyword,
                    "Video Title": title, 
                    "AI Strategy": analysis, 
                    "Source Used": source_used,
                    "URL": link
                })
                time.sleep(1) 
        except: pass
        return video_data

    def generate_ai_questions(self, keyword):
        if not self.use_ai: return []
        prompt = f"List 5 specific, high-value technical SEO questions about '{keyword}'. Return only the questions."
        try:
            completion = self.groq_client.chat.completions.create(
                messages=[{"role":"user", "content": prompt}],
                model="llama-3.1-8b-instant", temperature=0.7, max_tokens=150
            )
            raw_text = completion.choices[0].message.content
            questions = [q.strip('- ').strip() for q in raw_text.split('\n') if '?' in q]
            return questions[:5]
        except: return []

    def research_and_answer(self, question):
        search_payload = json.dumps({"q": question, "num": 3})
        context = ""
        sources = []
        try:
            resp = requests.post("https://google.serper.dev/search", headers=self.headers, data=search_payload)
            for i, res in enumerate(resp.json().get("organic", [])):
                context += f"Source {i+1}: {res.get('snippet')} (URL: {res.get('link')})\n"
                sources.append(res.get('link'))
        except: return "Search Failed", "N/A"

        prompt = f"Question: {question}\nData:\n{context}\nTask: Answer using the data. Cite sources."
        try:
            completion = self.groq_client.chat.completions.create(
                messages=[{"role":"user", "content": prompt}],
                model="llama-3.1-8b-instant", temperature=0.5, max_tokens=400
            )
            return completion.choices[0].message.content, "\n".join(sources)
        except: return "AI Error", "N/A"

    def generate_user_persona(self, keyword, community_data, youtube_data):
        if not self.use_ai: return "AI Not Active"

        pain_points = "\n- ".join([c['Question'] for c in community_data[:15]])
        interests = "\n- ".join([v['Video Title'] for v in youtube_data[:10]])

        prompt = f"""
        Act as a Senior Strategist. Create a detailed USER PERSONA for '{keyword}'.
        DATA SOURCE (PAIN POINTS): {pain_points}
        DATA SOURCE (INTERESTS): {interests}
        
        Output exact sections: 
        1. NAME & ROLE
        2. DEMOGRAPHICS
        3. PSYCHOGRAPHICS
        4. BEHAVIOR
        5. CONTENT STYLE
        """
        try:
            completion = self.groq_client.chat.completions.create(
                messages=[{"role":"user", "content": prompt}],
                model="llama-3.1-8b-instant", temperature=0.6, max_tokens=800
            )
            return completion.choices[0].message.content
        except: return "Error generating persona"

    def generate_content_brief(self, keyword, persona_text):
        if not self.use_ai: return [{"Brief": "AI Not Active"}]

        prompt = f"""
        Act as an SEO Content Strategist.
        
        CONTEXT:
        Target Keyword: {keyword}
        Target Audience Persona: {persona_text[:2000]}
        Target Word Count: 1500-2000 Words
        Keyword Density: 1.5%

        TASK 1: FILL THIS SEO TABLE
        - Recommended Title (Include '{keyword}', catchy)
        - Article Slug (URL friendly)
        - Meta Description (Include '{keyword}', enticing, under 160 chars)
        - H1 Tag (Includes '{keyword}')
        
        TASK 2: CREATE DETAILED BLOG STRUCTURE
        Create an outline (H2, H3). For EACH section provided:
        1. Content Suggestions: What to write? (Address persona pain points).
        2. Unique Insight: Add a unique angle or data point.
        3. Expert Commentary Idea: What topic should a writer get a quote on?
        4. Intent/Objective: What do we convey here?
        5. Keywords to use: List related keywords.
        6. Est Word Count for this section.

        TASK 3: FAQs
        - List 5 FAQs based on user intent.
        
        Format the output clearly.
        """

        try:
            completion = self.groq_client.chat.completions.create(
                messages=[{"role":"user", "content": prompt}],
                model="llama-3.1-8b-instant", temperature=0.5, max_tokens=1500
            )
            return [{"Content Brief": completion.choices[0].message.content}]
        except Exception as e:
            return [{"Content Brief": f"Error: {e}"}]

    def run(self, keywords):
        all_comp, all_comm, all_vids, all_qa = [], [], [], []
        persona_reports = []
        content_briefs = []
        
        for kw in keywords:
            # Phase 1-4 (Data Gathering)
            all_comp.extend([self.extract_page_data(u) for u in self.get_competitors(kw)])
            
            comm_data = self.get_community_questions(kw)
            all_comm.extend([
                {
                    "Keyword": kw, 
                    "Platform": c['Platform'],
                    "Question": c['Question'], 
                    "Link": c['Link']
                } 
                for c in comm_data
            ])
            
            vid_data = self.get_youtube_strategy(kw)
            all_vids.extend(vid_data)
            
            qa_qs = self.generate_ai_questions(kw)
            for q in qa_qs:
                ans, cites = self.research_and_answer(q)
                all_qa.append({"Keyword": kw, "Question": q, "Answer": ans, "Citations": cites})
                time.sleep(0.5)

            # Phase 5: Generate Persona
            persona_text = self.generate_user_persona(kw, comm_data, vid_data)
            persona_reports.append({"Keyword": kw, "User Persona": persona_text})

            # Phase 6: Generate Content Brief
            brief_text = self.generate_content_brief(kw, persona_text)
            content_briefs.extend(brief_text)

            time.sleep(1)

        return all_comp, all_comm, all_vids, all_qa, persona_reports, content_briefs

# ==========================================
# FLASK ROUTE
# ==========================================
@app.route('/generate', methods=['POST'])
def generate_report():
    data = request.json
    groq_key = data.get('groq_key')
    serper_key = data.get('serper_key')
    keywords = data.get('keywords')

    if not groq_key or not serper_key or not keywords:
        return jsonify({"error": "Missing API keys or keywords"}), 400

    try:
        engine = SEOIntelligenceHub(serper_key, groq_key)
        comp, comm, vids, qa, personas, briefs = engine.run(keywords)

        # Create Excel file in memory
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            if comp: pd.DataFrame(comp).to_excel(writer, sheet_name="Phase1_Competitors", index=False)
            if comm: pd.DataFrame(comm).to_excel(writer, sheet_name="Phase2_Community", index=False)
            if vids: pd.DataFrame(vids).to_excel(writer, sheet_name="Phase3_YouTube", index=False)
            if qa: pd.DataFrame(qa).to_excel(writer, sheet_name="Phase4_AI_Insights", index=False)
            if personas: pd.DataFrame(personas).to_excel(writer, sheet_name="Phase5_User_Persona", index=False)
            if briefs: pd.DataFrame(briefs).to_excel(writer, sheet_name="Phase6_Content_Brief", index=False)
        
        output.seek(0)
        return send_file(
            output, 
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True, 
            download_name='SEO_Master_Plan.xlsx'
        )

    except Exception as e:
        print(f"Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
