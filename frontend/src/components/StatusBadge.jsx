import { Badge } from "@/components/ui/badge"
import { cn } from "@/lib/utils"

const STATUS_LABELS = {
  entwurf: { label: 'Entwurf', className: 'bg-slate-500/20 text-slate-300 border-slate-500/30', dot: 'bg-slate-400' },
  kalkuliert: { label: 'Kalkuliert', className: 'bg-blue-500/20 text-blue-300 border-blue-500/30', dot: 'bg-blue-400' },
  angeboten: { label: 'Angeboten', className: 'bg-amber-500/20 text-amber-300 border-amber-500/30', dot: 'bg-amber-400' },
  beauftragt: { label: 'Beauftragt', className: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30', dot: 'bg-emerald-400' },
  abgeschlossen: { label: 'Abgeschlossen', className: 'bg-green-500/20 text-green-300 border-green-500/30', dot: 'bg-green-400' },
  verloren: { label: 'Verloren', className: 'bg-red-500/20 text-red-300 border-red-500/30', dot: 'bg-red-400' },
}

export default function StatusBadge({ status }) {
  const s = STATUS_LABELS[status] || { label: status, className: 'bg-gray-500/20 text-gray-300 border-gray-500/30', dot: 'bg-gray-400' }
  return (
    <Badge variant="outline" className={cn('inline-flex items-center gap-1.5 rounded-full text-xs font-medium', s.className)}>
      <span className={cn('w-1.5 h-1.5 rounded-full', s.dot)} />
      {s.label}
    </Badge>
  )
}

export { STATUS_LABELS }
