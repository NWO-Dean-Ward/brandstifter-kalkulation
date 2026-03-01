import { Card } from "@/components/ui/card"
import { cn } from "@/lib/utils"

export default function GlassCard({ children, className, ...props }) {
  return (
    <Card className={cn('glass-card', className)} {...props}>
      {children}
    </Card>
  )
}
