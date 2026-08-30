export const FLOW_STEPS = [
  { id: "connect", label: "Connect", path: "/accounts" },
  { id: "campaign", label: "Campaign", path: "/campaign" },
  { id: "strategy", label: "Content plan", path: "/strategy" },
  { id: "processing", label: "Processing", path: "/processing" },
];

export const PROCESSING_STEPS = [
  {
    id: "video",
    label: "Analyzing your podcast",
    description: "Locking the source so the original never gets overwritten.",
  },
  {
    id: "transcript",
    label: "Listening for interesting moments",
    description: "Finding the lines a viewer would actually stop for.",
  },
  {
    id: "highlight",
    label: "Identifying standout clips",
    description: "Keeping the hooks, payoffs, and educational segments.",
  },
  {
    id: "ranking",
    label: "Finding potential Shorts",
    description: "Different openings for Shorts, Reels, and posts.",
  },
  {
    id: "editing",
    label: "Editing and adapting clips",
    description: "Stitch, reframe, captions, and motion — a first draft you can ship.",
  },
  {
    id: "routing",
    label: "Fitting every platform",
    description: "Length, framing, and brand end screen matched to each channel.",
  },
  {
    id: "marketing",
    label: "Writing posts for each channel",
    description: "Hooks, captions, and CTAs rewritten per platform — not copy-pasted.",
  },
  {
    id: "planning",
    label: "Building your 30-day content strategy",
    description: "Each piece gets a date. You can pause a platform any time.",
  },
  {
    id: "packaging",
    label: "Packaging the campaign",
    description: "Final videos and copy, ready to review before anything goes live.",
  },
];

export const SHOW_TYPES = [
  {
    id: "auto",
    label: "Auto-detect",
  },
  {
    id: "comedy",
    label: "Comedy / panel show",
    detail: "Punchlines, speaker energy, and 1–2s of audience laughter after the joke.",
  },
  {
    id: "interview",
    label: "Insight interview",
    detail: "Bold statements first, then context. Keywords like money, crores, mistake, secret.",
  },
];

export const DEFAULT_CAMPAIGN = {
  sourceType: "url",
  source: "",
  brandName: "CreatorOS",
  website: "",
  tagline: "",
  endScreenEnabled: false,
  endScreenDuration: 3,
  endScreenTemplate: "logo_name_website",
  endScreenCta: "",
  goal: "Brand awareness",
  audience: "Startup founders",
  tone: "Professional",
  showType: "auto",
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

export const PLAN_PLATFORM_LABELS = {
  instagram_reels: "Instagram Reels",
  youtube_shorts: "YouTube Shorts",
  tiktok: "TikTok",
  linkedin: "LinkedIn",
  twitter: "X",
};

export const CALENDAR_PLATFORMS = {
  youtube_shorts: { short: "YT", label: "YouTube", tone: "red" },
  instagram_reels: { short: "IG", label: "Instagram", tone: "pink" },
  tiktok: { short: "TT", label: "TikTok", tone: "mint" },
  linkedin: { short: "in", label: "LinkedIn", tone: "blue" },
  twitter: { short: "X", label: "Twitter / X", tone: "slate" },
};
