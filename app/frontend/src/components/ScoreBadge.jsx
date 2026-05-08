export default function ScoreBadge({ score }) {
  if (score == null) return null

  const color =
    score >= 7.5
      ? 'border-score-high text-score-high'
      : score >= 5
      ? 'border-score-mid text-score-mid'
      : 'border-score-low text-score-low'

  return (
    <div className={`score-ring ${color}`}>
      {score.toFixed(1)}
    </div>
  )
}
