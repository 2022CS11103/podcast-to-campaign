import { useId } from "react";

export function BrandIcon({ platform, size = 18, label }) {
  const Mark = ICONS[platform] || ICONS[String(platform || "").split("_")[0]];
  if (!Mark) return null;
  return <Mark size={size} label={label} />;
}

function Svg({ size, label, children, viewBox = "0 0 24 24" }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox={viewBox}
      aria-label={label}
      role="img"
      focusable="false"
    >
      {children}
    </svg>
  );
}

function YouTubeMark({ size, label }) {
  return (
    <Svg size={size} label={label || "YouTube"}>
      <path
        fill="#FF0000"
        d="M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814z"
      />
      <path fill="#fff" d="M9.545 15.568V8.432L15.818 12z" />
    </Svg>
  );
}

function InstagramMark({ size, label }) {
  const gid = `ig-${useId().replace(/:/g, "")}`;
  return (
    <Svg size={size} label={label || "Instagram"}>
      <defs>
        <radialGradient id={gid} cx="30%" cy="107%" r="150%">
          <stop offset="0%" stopColor="#fdf497" />
          <stop offset="5%" stopColor="#fdf497" />
          <stop offset="45%" stopColor="#fd5949" />
          <stop offset="60%" stopColor="#d6249f" />
          <stop offset="90%" stopColor="#285AEB" />
        </radialGradient>
      </defs>
      <rect width="24" height="24" rx="6" fill={`url(#${gid})`} />
      <path
        fill="none"
        stroke="#fff"
        strokeWidth="1.8"
        d="M12 7.4A4.6 4.6 0 1 0 12 16.6 4.6 4.6 0 0 0 12 7.4z"
      />
      <rect
        x="7.1"
        y="7.1"
        width="9.8"
        height="9.8"
        rx="3.2"
        fill="none"
        stroke="#fff"
        strokeWidth="1.8"
      />
      <circle cx="16.6" cy="7.4" r="0.95" fill="#fff" />
    </Svg>
  );
}

function LinkedInMark({ size, label }) {
  return (
    <Svg size={size} label={label || "LinkedIn"}>
      <rect width="24" height="24" rx="4" fill="#0A66C2" />
      <path
        fill="#fff"
        d="M8.15 9.35H5.74V18.3h2.41zm-1.2-3.86a1.4 1.4 0 1 0 0 2.8 1.4 1.4 0 0 0 0-2.8zM18.26 12.2c0-1.86-.4-3.3-2.58-3.3-1.05 0-1.75.57-2.04 1.12h-.04V9.35h-2.31c.03.66 0 8.95 0 8.95h2.31v-5c0-.27.02-.53.1-.72.21-.53.7-1.08 1.51-1.08 1.07 0 1.5.81 1.5 2v4.8h2.31v-5.77z"
      />
    </Svg>
  );
}

function XMark({ size, label }) {
  return (
    <Svg size={size} label={label || "X"}>
      <rect width="24" height="24" rx="5" fill="#000" />
      <path
        fill="#fff"
        d="M16.6 6.2h1.92l-4.2 4.8 4.94 6.8h-3.87l-3.03-3.96-3.47 3.96H6.97l4.49-5.13-4.74-6.47h3.97l2.74 3.62 3.17-3.62zm-.67 10.4h1.06L8.13 7.27H6.99l8.94 9.33z"
      />
    </Svg>
  );
}

function TikTokMark({ size, label }) {
  return (
    <Svg size={size} label={label || "TikTok"}>
      <rect width="24" height="24" rx="6" fill="#010101" />
      <path
        fill="#25F4EE"
        d="M16.2 7.05c.72.7 1.58 1.2 2.54 1.42v2.18c-.9-.03-1.77-.26-2.56-.66v5.18c0 2.5-2.03 4.53-4.53 4.53-2.5 0-4.53-2.03-4.53-4.53s2.03-4.53 4.53-4.53c.16 0 .32.01.47.03v2.24a2.3 2.3 0 0 0-.47-.05 2.3 2.3 0 0 0-2.3 2.3 2.3 2.3 0 0 0 2.3 2.3 2.3 2.3 0 0 0 2.3-2.3V5.2h2.25c.04.63.23 1.24.55 1.85z"
      />
      <path
        fill="#FE2C55"
        d="M15.95 7.32c.72.7 1.58 1.2 2.54 1.42v2.18c-.9-.03-1.77-.26-2.56-.66v5.18c0 2.5-2.03 4.53-4.53 4.53-1.4 0-2.65-.64-3.47-1.64.72.86 1.8 1.4 3.01 1.4 2.5 0 4.53-2.03 4.53-4.53V7.32h.48z"
        transform="translate(.55 .35)"
      />
      <path
        fill="#fff"
        d="M16.2 7.05c.72.7 1.58 1.2 2.54 1.42v2.18c-.9-.03-1.77-.26-2.56-.66v5.18c0 2.5-2.03 4.53-4.53 4.53-2.5 0-4.53-2.03-4.53-4.53s2.03-4.53 4.53-4.53c.16 0 .32.01.47.03v2.24a2.3 2.3 0 0 0-.47-.05 2.3 2.3 0 0 0-2.3 2.3 2.3 2.3 0 0 0 2.3 2.3 2.3 2.3 0 0 0 2.3-2.3V5.2h2.25c.04.63.23 1.24.55 1.85z"
      />
    </Svg>
  );
}

const ICONS = {
  youtube_shorts: YouTubeMark,
  youtube: YouTubeMark,
  instagram_reels: InstagramMark,
  instagram: InstagramMark,
  linkedin: LinkedInMark,
  twitter: XMark,
  tiktok: TikTokMark,
};
