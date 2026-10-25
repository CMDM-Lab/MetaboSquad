/**
 * Maps the backend's `writer({"status": ...})` English original text to the
 * Chinese step name shown in the UI.
 * Source lines (do not edit the backend, only this table):
 *   literature_scoping_only_pubmed.py:29,43,54,89,155,190,245,382
 *   analysis_graph.py:62,106,130,154,178,258,337,503
 *   plot_graph.py:139,211,257
 *   id_mapping_graph.py:29,99
 *
 * Uses a prefix match, because some statuses carry a dynamic suffix (e.g. a
 * count).
 */

const ZH_PREFIX_MAP: ReadonlyArray<readonly [string, string]> = [
  ["expand_query", "展開查詢關鍵字"],
  ["Now searching in progress", "正在檢索文獻"],
  ["Merge complete, now title filtering", "合併完成，篩選標題中"],
  ["Title filtering complete, now abstract filtering", "標題篩選完成，篩選摘要中"],
  ["Literature search completed, summary now in progress", "文獻檢索完成，整理摘要中"],
  ["Summary completed, report writing now in progress", "摘要完成，撰寫報告中"],
  ["Report writing complete. Generating plots", "報告完成，繪製圖表中"],

  ["Parameter extraction complete, statistical analysis in progress", "參數擷取完成，統計分析中"],
  ["Statistical analysis completed, significant metabolite data extraction in progress", "統計分析完成，擷取顯著代謝物中"],
  ["Significant metabolite data extraction completed", "顯著代謝物擷取完成"],
  ["Feature extraction complete, mummichog analysis in progress", "特徵擷取完成，Mummichog 分析中"],
  ["Feature extraction complete, PubChem search in progress", "特徵擷取完成，查詢 PubChem 中"],
  ["PubChem search complete, Pathway analysis in progress", "PubChem 查詢完成，路徑分析中"],
  ["Pathway analysis completed, report writing now in progress", "路徑分析完成，撰寫報告中"],
  ["Summary complete! Ready to download", "全部完成，可以下載了"],

  ["Plot review is in progress", "圖表審查中"],
  ["Report writing now in progress", "撰寫報告中"],
  ["Report writing complete", "報告撰寫完成"],

  ["ID mapping in progress", "查詢代謝物 ID 中"],
];

export function statusLabel(raw: string, locale: string): string {
  if (locale === "en") return raw;
  for (const [prefix, label] of ZH_PREFIX_MAP) {
    if (raw.startsWith(prefix)) return label;
  }
  return raw;
}
