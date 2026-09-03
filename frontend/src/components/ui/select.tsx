import { Select as Primitive } from "@base-ui/react/select"
import { Check, ChevronDown } from "lucide-react"

import { cn } from "@/lib/utils"

const Select = Primitive.Root

function SelectTrigger({ className, children, ...props }: Primitive.Trigger.Props) {
  return <Primitive.Trigger className={cn("flex h-11 w-full items-center justify-between rounded-md border border-input bg-card px-3 text-sm shadow-xs outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}>{children}<Primitive.Icon render={<ChevronDown className="size-4 text-muted-foreground" />} /></Primitive.Trigger>
}
function SelectValue(props: Primitive.Value.Props) { return <Primitive.Value {...props} /> }
function SelectContent({ className, children, ...props }: Primitive.Popup.Props) {
  return <Primitive.Portal><Primitive.Positioner sideOffset={6} className="z-50"><Primitive.Popup className={cn("max-h-72 min-w-40 overflow-auto rounded-lg border border-border bg-popover p-1 text-popover-foreground shadow-lg", className)} {...props}><Primitive.List>{children}</Primitive.List></Primitive.Popup></Primitive.Positioner></Primitive.Portal>
}
function SelectItem({ className, children, ...props }: Primitive.Item.Props) {
  return <Primitive.Item className={cn("relative flex min-h-11 cursor-default items-center rounded-md py-2 pr-8 pl-2 text-sm outline-none data-highlighted:bg-accent data-highlighted:text-accent-foreground data-disabled:opacity-50", className)} {...props}><Primitive.ItemText>{children}</Primitive.ItemText><Primitive.ItemIndicator className="absolute right-2"><Check className="size-4" /></Primitive.ItemIndicator></Primitive.Item>
}
export { Select, SelectTrigger, SelectValue, SelectContent, SelectItem }
