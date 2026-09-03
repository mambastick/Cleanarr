import { cva, type VariantProps } from "class-variance-authority"
import { GithubIcon, StarIcon } from "lucide-react"
import { motion, useReducedMotion, type HTMLMotionProps } from "motion/react"
import { useEffect, useState } from "react"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium outline-none transition-[box-shadow,color,background-color,border-color] focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow-xs hover:bg-primary/90",
        accent: "bg-accent text-accent-foreground shadow-xs hover:bg-accent/90",
        outline: "border bg-background shadow-xs hover:bg-accent hover:text-accent-foreground",
        ghost: "hover:bg-accent hover:text-accent-foreground",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 gap-1.5 px-3",
        lg: "h-10 px-6",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
)

type GitHubStarsButtonProps = Omit<HTMLMotionProps<"a">, "children" | "href"> &
  VariantProps<typeof buttonVariants> & {
    username: string
    repo: string
    value?: number
    delay?: number
    hoverScale?: number
    tapScale?: number
  }

function GitHubStarsButton({
  className,
  username,
  repo,
  value,
  delay = 0,
  variant,
  size,
  hoverScale = 1.04,
  tapScale = 0.96,
  ...props
}: GitHubStarsButtonProps) {
  const reducedMotion = useReducedMotion()
  const [stars, setStars] = useState(value ?? 0)

  useEffect(() => {
    if (value !== undefined) {
      setStars(value)
      return
    }

    const controller = new AbortController()
    const timeout = window.setTimeout(() => {
      void fetch(`https://api.github.com/repos/${username}/${repo}`, { signal: controller.signal })
        .then((response) => response.json())
        .then((data: unknown) => {
          if (typeof data === "object" && data !== null && "stargazers_count" in data && typeof data.stargazers_count === "number") {
            setStars(data.stargazers_count)
          }
        })
        .catch(() => undefined)
    }, delay)

    return () => {
      window.clearTimeout(timeout)
      controller.abort()
    }
  }, [delay, repo, username, value])

  return (
    <motion.a
      href={`https://github.com/${username}/${repo}`}
      target="_blank"
      rel="noreferrer noopener"
      className={cn(buttonVariants({ variant, size }), className)}
      whileHover={reducedMotion ? undefined : { scale: hoverScale }}
      whileTap={reducedMotion ? undefined : { scale: tapScale }}
      {...props}
    >
      <GithubIcon aria-hidden="true" />
      <motion.span
        key={stars}
        initial={reducedMotion ? false : { y: 5, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ type: "spring", stiffness: 350, damping: 35 }}
        className="tabular-nums"
      >
        {stars}
      </motion.span>
      <motion.span
        initial={false}
        animate={reducedMotion ? undefined : { rotate: [0, -10, 0], scale: [1, 1.12, 1] }}
        transition={{ delay: 0.12, duration: 0.35 }}
        aria-hidden="true"
      >
        <StarIcon className="fill-current text-status-warning" />
      </motion.span>
    </motion.a>
  )
}

export { GitHubStarsButton, type GitHubStarsButtonProps }
