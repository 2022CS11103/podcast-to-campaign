export const FLOW_STEPS = [
  { id: "connect", label: "Connect", path: "/" },
  { id: "campaign", label: "Campaign", path: "/campaign" },
  { id: "strategy", label: "Content plan", path: "/strategy" },
  { id: "processing", label: "Processing", path: "/processing" },
];

export const PROCESSING_STEPS = [
  {
    id: "video",
    label: "Ingesting the talk",
    description: "Securing the source and checking picture and audio quality.",
  },
  {
    id: "transcript",
    label: "Watching and listening",
    description: "Reading the words, scene changes, motion, and loud beats together.",
  },
  {
    id: "highlight",
    label: "Scoring standout moments",
    description: "Ranking hooks, clarity, emotion, novelty, and visual energy.",
  },
  {
    id: "ranking",
    label: "Choosing distinct cuts",
    description: "Separating Shorts and Reels so every opening earns attention.",
  },
  {
    id: "editing",
    label: "Directing the edit",
    description: "Planning jump cuts, punch-ins, captions, and keyword emphasis.",
  },
  {
    id: "routing",
    label: "Adapting every platform",
    description: "Matching format, duration, framing, and intent to each channel.",
  },
  {
    id: "marketing",
    label: "Writing campaign copy",
    description: "Creating platform-native hooks, captions, titles, and CTAs.",
  },
  {
    id: "planning",
    label: "Building the calendar",
    description: "Spacing content across the campaign without repeating the same angle.",
  },
  {
    id: "packaging",
    label: "Packaging your campaign",
    description: "Rendering final assets and preparing the downloadable campaign kit.",
  },
];

export const DEFAULT_CAMPAIGN = {
  sourceType: "url",
  source: "",
  brandName: "CreatorOS",
  website: "",
  goal: "Brand awareness",
  audience: "Startup founders",
  tone: "Professional",
  durationDays: 30,
  startDate: new Date().toISOString().slice(0, 10),
};

export const DEFAULT_PLAN = {
  instagram_reels: {
    enabled: true,
    count: 5,
    interval_days: 3,
    purpose: "Build reach",
    suggested: "15–45 sec",
  },
  youtube_shorts: {
    enabled: true,
    count: 5,
    interval_days: 4,
    purpose: "Grow subscribers",
    suggested: "30–60 sec",
  },
  linkedin: {
    enabled: true,
    count: 8,
    interval_days: 3,
    purpose: "Build authority",
    suggested: "500–1,200 words",
  },
  twitter: {
    enabled: true,
    count: 12,
    interval_days: 2,
    purpose: "Start conversations",
    suggested: "5–15 posts",
  },
};

export const PLATFORM_META = {
  youtube: { name: "YouTube", detail: "Shorts + long-form", tone: "red" },
  instagram: { name: "Instagram", detail: "Reels + carousels", tone: "pink" },
  linkedin: { name: "LinkedIn", detail: "Authority posts", tone: "blue" },
  twitter: { name: "Twitter / X", detail: "Threads + replies", tone: "slate" },
};
