import { Switch as Primitive } from "@base-ui/react/switch"
import { cn } from "@/lib/utils"

function Switch({ className, ...props }: Primitive.Root.Props) {
  return <Primitive.Root className={cn("group relative inline-flex size-11 items-center justify-center rounded-lg bg-transparent outline-none focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}><span aria-hidden="true" className="pointer-events-none absolute h-5 w-9 rounded-full bg-input transition-colors group-data-[checked]:bg-primary" /><Primitive.Thumb className="absolute left-[6px] top-1/2 size-4 -translate-y-1/2 rounded-full bg-card shadow-sm transition-transform data-checked:translate-x-4" /></Primitive.Root>
}
export { Switch }
