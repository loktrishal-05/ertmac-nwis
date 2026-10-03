// Pure helpers for the in-browser Qwen summary (kept free of transformers.js so node --test can import them).
export const MODELS = [
  { id: 'onnx-community/Qwen3.5-4B-ONNX-OPT', label: 'Qwen 3.5 4B', downloadGb: 2.8 },
  { id: 'onnx-community/Qwen3.5-2B-ONNX-OPT', label: 'Qwen 3.5 2B', downloadGb: 1.4 },
]

// navigator.deviceMemory is coarse (Chrome caps it at 8 GB); below 8 GB the 4B model rarely fits, so start at 2B.
export const pickModels = deviceMemoryGb => (deviceMemoryGb != null && deviceMemoryGb < 8 ? MODELS.slice(1) : MODELS)

const line = (item, i) => [`[${i + 1}] ${item.event_id || item.report_id || item.well_id}`,
  item.well_id && `well ${item.well_id}`, item.report_id && `report ${item.report_id}${item.page != null ? ` p.${item.page}` : ''}`,
  item.depth_tvd_m != null ? `${item.depth_tvd_m} m TVD` : item.depth_md_m != null && `${item.depth_md_m} m MD`,
  item.formation, item.excerpt && `"${item.excerpt}"`, item.mitigation && `mitigation: ${item.mitigation}`].filter(Boolean).join(' | ')

// Grounded prompt: the model may only restate the cited evidence it is given, and must cite by [n].
export function buildMessages(question, items, limit = 8) {
  const evidence = items.slice(0, limit)
  return [
    { role: 'system', content: 'You summarise historical drilling evidence for a drilling engineer. Use ONLY the numbered evidence. '
      + 'Cite every statement with its number, e.g. [2]. If the evidence does not answer the question, say so. '
      + 'Be concise (under 150 words). This is advisory decision support; never instruct rig operations.' },
    { role: 'user', content: `Question: ${question}\n\nEvidence:\n${evidence.map(line).join('\n')}` },
  ]
}
