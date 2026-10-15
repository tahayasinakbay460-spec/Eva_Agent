import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 22, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...rest,
  };
}

export const ChatIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.4-4.2A8 8 0 1 1 21 12Z" />
  </svg>
);
export const MicIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="9" y="3" width="6" height="11" rx="3" />
    <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
  </svg>
);
export const VideoIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3" y="6" width="13" height="12" rx="3" />
    <path d="m16 10 5-3v10l-5-3" />
  </svg>
);
export const HeartIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 21s-7-4.4-9-9a5 5 0 0 1 9-3 5 5 0 0 1 9 3c-2 4.6-9 9-9 9Z" />
  </svg>
);
export const InfinityIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M7 8a4 4 0 0 0 0 8c3 0 4-4 5-4s2-4 5-4a4 4 0 0 1 0 8c-3 0-4-4-5-4s-2 4-5 4" />
  </svg>
);
export const LockIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="5" y="11" width="14" height="10" rx="2" />
    <path d="M8 11V7a4 4 0 0 1 8 0v4" />
  </svg>
);
export const HomeIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m3 11 9-8 9 8v9a2 2 0 0 1-2 2h-4v-6H9v6H5a2 2 0 0 1-2-2v-9Z" />
  </svg>
);
export const ChartIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
  </svg>
);
export const CompassIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="m15.5 8.5-2 5-5 2 2-5 5-2Z" />
  </svg>
);
export const UserIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21a8 8 0 0 1 16 0" />
  </svg>
);
export const BellIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 16V11a6 6 0 1 1 12 0v5l2 2H4l2-2ZM10 20a2 2 0 0 0 4 0" />
  </svg>
);
export const ChevronRight = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="m9 6 6 6-6 6" />
  </svg>
);
export const ArrowLeft = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M19 12H5m7-7-7 7 7 7" />
  </svg>
);
export const SendIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M22 2 11 13M22 2 15 22l-4-9-9-4 20-7Z" />
  </svg>
);
export const SparkIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M6 18l2.5-2.5M15.5 8.5 18 6" />
  </svg>
);
export const SmileIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M8.5 14.5s1.2 2 3.5 2 3.5-2 3.5-2M9 10h.01M15 10h.01" />
  </svg>
);
export const LeafIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 20c0-9 5-14 16-16-1 11-6 16-16 16Zm0 0 8-8" />
  </svg>
);
export const MaskIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M4 6c5-2 11-2 16 0v6c0 5-4 8-8 9-4-1-8-4-8-9V6Z" />
    <path d="M8.5 11h.01M15.5 11h.01M9 15c2 1.3 4 1.3 6 0" />
  </svg>
);
