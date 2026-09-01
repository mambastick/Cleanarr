import { Checkbox as Primitive } from "@base-ui/react/checkbox"
import { Check } from "lucide-react"
import { cn } from "@/lib/utils"

function Checkbox({ className, ...props }: Primitive.Root.Props) {
  return <Primitive.Root className={cn("grid size-4 shrink-0 place-items-center rounded border border-input bg-card text-primary outline-none focus-visible:ring-3 focus-visible:ring-ring/50 data-checked:border-primary data-checked:bg-primary data-checked:text-primary-foreground disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}><Primitive.Indicator><Check className="size-3.5" /></Primitive.Indicator></Primitive.Root>
}
export { Checkbox }
