import { useId } from "react";

// The Marketing AI mark: a cream "M" that rises like a growth line, on a wine clay tile,
// with a gold spark. The same drawing is the browser tab icon (public/favicon.svg).
export default function BrandMark({ size = 36, className = "" }) {
  const id = useId();

  return (
    <svg
      className={`brand-mark ${className}`}
      width={size}
      height={size}
      viewBox="0 0 64 64"
      aria-hidden="true"
      focusable="false"
    >
      <defs>
        <linearGradient id={`${id}-tile`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#c0475a" />
          <stop offset="1" stopColor="#7b1e2b" />
        </linearGradient>
      </defs>
      <rect x="2" y="2" width="60" height="60" rx="18" fill={`url(#${id}-tile)`} />
      <path d="M8 10 Q32 2 56 10" stroke="#ffd9d9" strokeOpacity=".35" strokeWidth="3" fill="none" strokeLinecap="round" />
      <path
        d="M17 45 V23 L32 37 L47 23 V45"
        stroke="#f5e8d0"
        strokeWidth="6.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle className="brand-spark" cx="49" cy="14" r="4.5" fill="#e9c98f" />
    </svg>
  );
}
