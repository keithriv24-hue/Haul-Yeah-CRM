import * as React from "react"
import { Slot } from "@radix-ui/react-slot"
import { cva } from "class-variance-authority";

import { cn } from "@/lib/utils"

/**
 * Button hierarchy, in order of loudness:
 *   accent   — the one thing to do on this panel. Orange. Never more than one.
 *   default  — navy. Structural / confirming actions.
 *   outline  — the common case. Quiet until you touch it.
 *   ghost    — icon buttons, toolbar actions.
 *   link     — inline text actions.
 * Orange is reserved for actions. Status lives in badges, never in a button.
 */
const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-lg",
    "text-sm font-semibold",
    "transition-[background-color,border-color,color,box-shadow,transform] duration-[160ms] ease-out-soft",
    "active:scale-[0.975] motion-reduce:active:scale-100",
    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
    "disabled:pointer-events-none disabled:opacity-45",
    "[&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  ].join(" "),
  {
    variants: {
      variant: {
        default:
          "bg-primary text-primary-foreground hover:bg-primary/90",
        accent:
          "bg-accent text-accent-foreground hover:bg-accent-press shadow-sm",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90",
        outline:
          "border border-border-strong bg-surface text-ink hover:bg-surface-sunk hover:border-border-strong",
        secondary:
          "bg-surface-sunk text-secondary-foreground hover:bg-muted",
        ghost:
          "text-ink-2 hover:bg-surface-sunk hover:text-ink",
        link:
          "text-primary underline-offset-4 hover:underline h-auto p-0",
      },
      size: {
        default: "h-11 px-4 md:h-10",
        sm: "h-9 rounded-md px-3 text-[13px]",
        lg: "h-12 px-6 text-[15px]",
        band: "action-band w-full",
        icon: "h-10 w-10 md:h-9 md:w-9",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
)

const Button = React.forwardRef(({ className, variant, size, asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button"
  return (
    <Comp
      className={cn(buttonVariants({ variant, size, className }))}
      ref={ref}
      {...props} />
  );
})
Button.displayName = "Button"

export { Button, buttonVariants }
