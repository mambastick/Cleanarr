import { Progress as Primitive } from "@base-ui/react/progress"
import { cn } from "@/lib/utils"
function Progress({ className, value, ...props }: Primitive.Root.Props) { return <Primitive.Root value={value} className={cn("block", className)} {...props}><Primitive.Track className="h-2 overflow-hidden rounded-full bg-muted"><Primitive.Indicator data-slot="progress-indicator" className={cn("h-full bg-primary transition-[width] duration-200", value == null && "hidden")} /></Primitive.Track></Primitive.Root> }
export { Progress }
