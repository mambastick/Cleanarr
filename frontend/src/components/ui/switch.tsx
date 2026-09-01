import { Switch as Primitive } from "@base-ui/react/switch"
import { cn } from "@/lib/utils"

function Switch({ className, ...props }: Primitive.Root.Props) {
  return <Primitive.Root className={cn("inline-flex h-5 w-9 rounded-full bg-input p-0.5 outline-none transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 data-checked:bg-primary disabled:cursor-not-allowed disabled:opacity-50", className)} {...props}><Primitive.Thumb className="size-4 rounded-full bg-card transition-transform data-checked:translate-x-4" /></Primitive.Root>
}
export { Switch }
