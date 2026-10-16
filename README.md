<!--
  The images in assets/ and the sections between the "live:" markers are
  regenerated every hour by .github/workflows/profile.yml from live GitHub data.
  Everything else in this file is hand-written: edit it freely.
-->

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/agent-trace-dark.svg">
  <img alt="Agent run log: who I am, my latest repos, last 30 days of activity and top languages, refreshed hourly" src="assets/agent-trace-light.svg" width="100%">
</picture>

## Nikhil Reddy · AI Engineer

I build production LLM systems: retrieval, multi-agent pipelines, and agents that operate real software. I've spent 3+ years doing it across healthcare and financial services, and I'm now a **Data Scientist at Echelon Insights**.

I put deterministic guardrails outside the model wherever correctness matters, and I ship with eval harnesses, drift monitoring and release ownership.

<p>
  <a href="https://www.linkedin.com/in/uvnikhil"><img alt="LinkedIn" src="https://img.shields.io/badge/LinkedIn-uvnikhil-0A66C2?style=flat-square&logo=linkedin&logoColor=white"></a>
  <a href="mailto:nikhilreddyulindala@gmail.com"><img alt="Email" src="https://img.shields.io/badge/Email-nikhilreddyulindala%40gmail.com-EA4335?style=flat-square&logo=gmail&logoColor=white"></a>
  <img alt="Profile views" src="https://komarev.com/ghpvc/?username=nikhilreddy00&style=flat-square&color=39c5bb&label=profile+views">
</p>

### Featured builds

<table>
  <tr>
    <td width="50%" valign="top">
      <a href="https://github.com/nikhilreddy00/praxis"><b>Praxis</b></a> · record once, replay many<br><br>
      An LLM drives legacy back-office software through Playwright once. After that, the recorded workflow replays deterministically with no model in the loop, and a test enforces that guarantee. It has policy guardrails, a human takeover path, and an MCP server that exposes only approved capabilities. 624 tests passing.<br><br>
      <code>TypeScript</code> <code>Playwright</code> <code>MCP</code>
    </td>
    <td width="50%" valign="top">
      <a href="https://github.com/nikhilreddy00/AnalystAI"><b>AnalystAI</b></a> · multi-agent data analyst<br><br>
      Upload a raw CSV and a 7-agent LangGraph pipeline writes Python, runs it in an E2B sandbox, and returns charts with written insight. Chart selection and quality gates stay deterministic Python rather than model calls.<br><br>
      <code>LangGraph</code> <code>FastAPI</code> <code>Next.js</code> <code>Qdrant</code> <code>Postgres</code>
    </td>
  </tr>
</table>

### Latent space of my work

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/latent-space-dark.svg">
  <img alt="Map of my public repositories, placed by what they are about and grouped into clusters" src="assets/latent-space-light.svg" width="100%">
</picture>

<sub>Every public repo is embedded from its README, description and topics (TF-IDF → LSA), clustered with k-means, and projected to 2-D. A new repo appears on the map within the hour.</sub>

### Recently shipped

<!--live:recent:start-->
| Project | What it does | Language | Last push |
| :-- | :-- | :-- | :-- |
| [**clinic-voice-agent**](https://github.com/nikhilreddy00/clinic-voice-agent) ★2 | 📞 An always-on AI voice agent that answers a real phone and books clinic appointments end-to-end… | Python | Sep 07, 2026 |
| [**student-mental-health-ews**](https://github.com/nikhilreddy00/student-mental-health-ews) | 🎓 AI-powered early warning system detecting struggling university students weeks before crisis… | Jupyter Notebook | Aug 22, 2026 |
| [**outbound-clinic-voice-agent**](https://github.com/nikhilreddy00/outbound-clinic-voice-agent) | AI voice agent that calls patients after hospital discharge, screens for warning signs, and… | Python | Aug 02, 2026 |
| [**mirofish-meta-layoffs**](https://github.com/nikhilreddy00/mirofish-meta-layoffs) | AI-powered multi-agent simulation of Meta's April 2026 layoffs — 26 stakeholder agents, 720… | Python | May 01, 2026 |
| [**sec-finance-rag**](https://github.com/nikhilreddy00/sec-finance-rag) | Production RAG chatbot over 25,000+ SEC EDGAR filings (S&P 500) — Claude · BGE · Hybrid BM25+Dense… | HTML | Apr 28, 2026 |
<!--live:recent:end-->

### Training run

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/training-run-dark.svg">
  <img alt="Activity dashboard: daily contributions over 90 days, new repos as checkpoints, language mix, streaks and totals" src="assets/training-run-light.svg" width="100%">
</picture>

### Experience

| When | Role | Highlights |
| :-- | :-- | :-- |
| Sep 2026 – now | **Data Scientist** · Echelon Insights | |
| Jan 2025 – Aug 2026 | **AI Engineer** · Milken Institute School of Public Health, GWU | Hybrid BM25 + embedding retrieval with cross-encoder reranking over 15K behavioral-health records (RAGAS answer relevancy 0.61 → 0.82). Fine-tuned BERT classifier (macro-F1 0.68 → 0.84). SageMaker endpoint p95 2.8 s → 1.4 s, run in production for 11 months. |
| Aug – Dec 2024 | **Data Science Consultant** · Data Science for Sustainable Development | FAISS semantic search across JSON, CSV and Parquet that surfaced ~1,200 mismatched records. PySpark feature pipelines on Databricks cut study prep from two days to four hours. |
| May 2023 – May 2024 | **Data Scientist, Conversational AI** · Cogno AI (acquired by Exotel) | Intent classification across 40+ banking intents (macro-F1 0.71 → 0.86). Agent-assist retrieval over 10K documents (top-3 relevance 62% → 84%). FastAPI serving at 380 ms p95. |

### Toolbox

```yaml
agents:     LangGraph · CrewAI · MCP · tool calling · human-in-the-loop · guardrails
retrieval:  hybrid BM25 + dense · reranking · chunking · Qdrant · FAISS · ChromaDB · Pinecone
models:     Claude · GPT · Llama · BERT · LoRA / QLoRA · PyTorch · Hugging Face · XGBoost
evals:      RAGAS · DeepEval · LangSmith · LLM-as-judge · A/B testing · drift detection
shipping:   FastAPI · Docker · AWS (SageMaker, Bedrock, Lambda, S3) · MLflow · GitHub Actions
stack:      Python · TypeScript · SQL · PySpark · Next.js · Postgres · Databricks · Snowflake
```

**Education:** MS Data Analytics, The George Washington University (2026) · B.Tech Computer Science, Dayananda Sagar University (2024)

---

<sub>The visuals on this page are rebuilt every hour by a GitHub Action from live GitHub data. Private repositories count toward totals only and are never named. Last update: <!--live:updated:start-->2026-10-16 02:32 UTC<!--live:updated:end--></sub>
