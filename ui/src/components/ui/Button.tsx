import { clsx } from "clsx";

type Variant = "primary" | "danger" | "ghost" | "success";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: "sm" | "md";
}

const variants: Record<Variant, string> = {
  primary: "bg-zinc-700 hover:bg-zinc-600 text-zinc-100 border border-zinc-600",
  danger: "bg-red-900/60 hover:bg-red-800/70 text-red-200 border border-red-700",
  ghost: "hover:bg-zinc-800 text-zinc-400 hover:text-zinc-100",
  success: "bg-emerald-900/60 hover:bg-emerald-800/70 text-emerald-200 border border-emerald-700",
};

const sizes = {
  sm: "px-2.5 py-1 text-xs",
  md: "px-4 py-1.5 text-sm",
};

export function Button({
  variant = "primary",
  size = "md",
  className,
  disabled,
  children,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled}
      className={clsx(
        "inline-flex items-center gap-1.5 rounded font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-zinc-500",
        variants[variant],
        sizes[size],
        disabled && "opacity-40 cursor-not-allowed",
        className,
      )}
    >
      {children}
    </button>
  );
}
