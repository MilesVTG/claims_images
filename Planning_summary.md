# Claims Photo AI Analysis — Planning Summary

## Summary

After AI-assisted research across the top enterprise AI platforms, **Gemini Business/Enterprise is the clear best-in-class choice for photo-based claims fraud detection.** It leads in native image metadata extraction, damage analysis, reverse-image lookup integration, and scalable batch processing — all within the Google Cloud ecosystem we are already targeting. Our M.I.L.E.S. AI foundation may be combined with Gemini (or other platforms) depending on the specific use case (Claims, general use, BI, etc.). WatsonxAI was excluded from this analysis; further research is needed on that platform.

---

## Section 1 — AI Platform Landscape

Gemini Enterprise outperforms its peers specifically for photo-based claims workflows.

- **A.** **Platforms evaluated:** Gemini Business/Enterprise, ChatGPT Enterprise, Claude Enterprise, Grok Business/Enterprise
- **B.** **Excluded:** WatsonxAI (requires further research)
- **C.** **Winner:** Gemini Business/Enterprise — decisive advantage in photo understanding, metadata extraction, and Google Cloud-native integration
- **D.** **Strategy:** M.I.L.E.S. may be paired with one or more external platforms depending on use case

---

## Section 2 — Photo Metadata & Fraud Detection Capabilities

Gemini extracts EXIF data natively and can cross-reference it against claim details conversationally, without custom code.

- **A.** Extracts exact EXIF fields: `DateTimeOriginal`, GPS lat/long, device info — no custom code required
- **B.** Example prompt: *"Extract timestamp and GPS from this photo, convert GPS to address, compare to service drive at [address] and loss date [date]. Flag mismatches outside a 24–48 hr window."*
- **C.** Detects **recycled/duplicate photos** via visual similarity reasoning (damage patterns, lighting, angles)
- **D.** Detects **staged/fake damage** via physics and lighting consistency checks (inconsistent shadows, editing artifacts, healing vs. fresh damage)
- **E.** Validates **consistency with claim description**
- **F.** **Recommended pre-pass:** Run Cloud Vision API (cheap) to extract EXIF timestamp + GPS first, then feed into Gemini batch prompt for auditable, rock-solid fraud flagging

---

## Section 3 — Reverse Image Lookup Integration

Gemini on Google Cloud integrates natively with Google's reverse-image engine — a stronger capability than any competing platform.

- **A.** Uses **Cloud Vision API – Web Detection** (same tech as Google Images/Lens, but programmable)
- **B.** Finds exact or near-matches of submitted photos across the public web and returns source pages
- **C.** Can run on every photo or only on Gemini-flagged suspicious images (cost-effective)
- **D.** **Automated pipeline:**
  1. Photos land in Google Cloud Storage (GCS)
  2. Cloud Vision Web Detection runs → flags recycled/public-stock photos
  3. Gemini Batch Inference runs → deep fraud reasoning, damage validation, geo/timestamp cross-check
  4. Output lands in BigQuery with risk score, evidence, and reverse-image match links
- **E.** Claims team sees a clean dashboard: *"Photo #XYZ flagged as 92% likely recycled — matched to public listing from 2023, timestamp mismatch, damage inconsistent with reported date."*

---

## Section 4 — Batch Processing & Scale

Gemini handles hundreds of thousands of photos per job, making bulk back-testing and nightly runs practical.

- **A.** Single batch job handles **200,000+ photos**; million-photo prepopulation = multiple jobs
- **B.** Batch turnaround: ~24 hours after processing starts
- **C.** Batch mode is **~50% cheaper** than real-time API calls
- **D.** Real-time processing for new claims: **seconds per claim**
- **E.** **Simplified alternative via BigQuery + Object Tables** (no code required for basic analysis):
  1. Point BigQuery at your GCS bucket
  2. Run SQL queries that call Gemini on every image
  3. Results land directly in BigQuery/Sheets for the claims team

---

## Section 5 — Storage & Compliance

All images and results stay within Google Cloud — no repeated uploads, no data used for model training.

- **A.** Store in **Google Cloud Storage** (or Google Drive for Workspace users)
- **B.** Gemini and Vision API read directly from GCS — zero extra storage movement or cost
- **C.** Storage is unlimited, cheap, secure, and highly durable
- **D.** Enterprise controls: encryption, access logs, retention policies
- **E.** Compliance: **SOC 2, HIPAA** (if needed), GDPR
- **F.** Data is **never used to train Google's models**

---

## Section 6 — Contract-Level Tracking & Cross-Claim Change Detection

Gemini, backed by Vertex AI and BigQuery, can track vehicle-level history across claims and auto-flag physical inconsistencies.

- **A.** Tracks photos per contract when structured claim history is fed via Vertex AI + BigQuery
- **B.** Detects changes such as:
  - **Tire brand** (reads logos/text: "Michelin," "Goodyear," "Continental")
  - **Vehicle color** ("blue sedan" on Claim 1 vs. "red" on Claim 3)
  - Damage patterns, wear consistency, rim style, license plate partials, background clues
- **C.** Flags inconsistencies as high-confidence fraud signals automatically
- **D.** Handles both bulk back-testing (batch) and real-time new claim analysis

---

## Section 7 — Real-World Proof: Avantia Group "Holmes" System

A production insurance deployment proves this exact workflow works at scale today.

- **A.** **Who:** Avantia Group (UK home insurer), built 2025
- **B.** **Stack:** Vertex AI + BigQuery + Gemini 2.5 Flash/Pro — identical to our target architecture
- **C.** **What it does:** Analyzes each new claim against full policy + claims history; flags photo and document inconsistencies across multiple claims per contract
- **D.** **Results:**
  - Fraud detection referral rate: **2% → 12% (6× increase)**
  - In ~50% of flagged cases, caught issues that saved money or accelerated legitimate payouts
  - POC to production: **~3 months**
  - Projected annual savings: **£1.2M**

---

## Section 8 — Cost & Rollout Approach

The recommended path is a small pilot using batch mode before scaling.

- **A.** Batch mode + **Gemini Flash** models keeps cost low even at hundreds of thousands of photos
- **B.** Recommended start: pilot of **1,000–5,000 photos** (completable in a day or two)
- **C.** Requires a **Google Cloud project with Vertex AI / Gemini Enterprise enabled**
- **D.** Competitors (xAI/Grok, Claude, ChatGPT) cannot match this workflow's native scale or Google reverse-image integration
