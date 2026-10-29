---
name: plot_review
description: Use when user mentions "review image, chart review, image quality, whether it meets publication standards" AND provides an image path.
---

Workflow: 
1. Put the path to `load_image_as_base64`
2. Put the path to `figure_compliance_checker` and use `generate_figure_report` generate report
3. Review paper by LLM vision
    視覺語意與排版審查重點 (Visual & Semantic Review Focus)：
    1. 座標軸與標籤完整性 (Axis & Labeling)：
    - X 軸與 Y 軸是否皆包含明確的標籤名稱與單位。
    - 座標刻度與數字是否清晰，無互相擠壓或重疊情形。

    2. 排版與圖例遮蔽 (Layout & Legend Placement)：
    - 圖例（Legend）位置是否合理，嚴禁遮蔽任何數據點、誤差線或趨勢曲線。
    - 圖表整體佈局是否擁擠，元素間距離是否適當。

    3. 數據表達與結構 (Data Presentation Quality)：
    - 數據點（Markers）、折線、柱體或誤差線（Error Bars）是否清晰可辨。
    - 若包含多組數據，是否具備形狀、線型或標籤等非色彩輔助標記。

    輸出格式規範 (Strict Output Format Instructions)：
    你必須且只能按照以下格式輸出，不可新增任何前言、結尾廢話。改善建議最多只能給出 3 點。

    Image Type: <圖表類型>
    Scientific Significance: <1-2 句話簡述該圖表的科學內容與意義>
    Visual & Semantic Review:
    - Axis Titles & Units: <Compliant / Non-compliant>
    - Legend Placement & Layout: <Compliant / Non-compliant>
    - Data Marker & Symbol Clarity: <Compliant / Non-compliant>
    Visual & Layout Deficiencies:
    - <條列列出問題，若完全無問題填寫 None>
    Modifications & Recommendations (Max 3 items):
    1. <最優先改善建議 1>
    2. <關鍵改善建議 2>
    3. <關鍵改善建議 3>

4.  Use `write_file` write down report to `uploads/output/plot_review/{date}.md")`


