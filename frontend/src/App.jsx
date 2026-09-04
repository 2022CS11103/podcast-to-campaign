import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useParams,
} from "react-router-dom";
import {
  ArrowLeft,
  ArrowRight,
  Ban,
  BarChart3,
  CalendarDays,
  Check,
  CheckCircle2,
  Clock3,
  Copy,
  Download,
  FileText,
  FileVideo,
  Film,
  Home,
  Link2,
  LoaderCircle,
  LogOut,
  Menu,
  Mic,
  Pause,
  Play,
  Plus,
  RefreshCw,
  Rocket,
  Settings2,
  Sparkles,
  Square,
  Trash2,
  Upload,
  X,
  Zap,
} from "lucide-react";
import { BrandingFields, brandPayloadFromForm, formFromBrand } from "./branding";
import { BrandIcon } from "./BrandIcon";
import { AuthProvider, useAuth } from "./auth";
import { apiUrl, creatorApi } from "./api";
import {
  DEFAULT_CAMPAIGN,
  DEFAULT_PLAN,
  FLOW_STEPS,
  PLATFORM_META,
  PROCESSING_STEPS,
  CALENDAR_PLATFORMS,
  PLAN_PLATFORM_LABELS,
  SHOW_TYPES,
} from "./campaign";
import LOGO_URL from "./assets/creatoros-mark.png";

function useStoredState(key, initialValue) {
  const [value, setValue] = useState(() => {
    try {
      const saved = localStorage.getItem(key);
      return saved ? JSON.parse(saved) : initialValue;
    } catch {
      return initialValue;
    }
  });
  useEffect(() => {
    localStorage.setItem(key, JSON.stringify(value));
  }, [key, value]);
  return [value, setValue];
}

function BrandMark({ size = 44, alt = "creatorOS" }) {
  return (
    <div className="brand-mark" style={{ width: size, height: size }}>
      <img src={LOGO_URL} alt={alt} />
    </div>
  );
}

function Logo() {
  return (
    <div className="brand">
      <BrandMark />
      <div>
        <strong>creator<span className="brand-os">OS</span></strong>
        <span className="brand-tagline">One video. A month of content.</span>
      </div>
    </div>
  );
}

function displayName(user) {
  const raw = user?.user_metadata?.full_name || user?.name || (user?.email || "").split("@")[0] || "there";
  return String(raw).split(/\s+/)[0];
}

function dayGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function AppShell({ children, step, flow = true }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const auth = useAuth();
  const user = auth.user;
  const activeIndex = FLOW_STEPS.findIndex((item) => item.id === step);
  const path = location.pathname;
  const navItems = [
    { to: "/", label: "Home", icon: Home, active: path === "/" },
    { to: "/campaign", label: "Content", icon: Film, active: path.startsWith("/campaign") || path.startsWith("/strategy") || path.startsWith("/processing") },
    { to: "/calendar", label: "Calendar", icon: CalendarDays, active: path.startsWith("/calendar") },
    { to: "/results/latest", label: "Library", icon: BarChart3, active: path.startsWith("/results") || path.startsWith("/complete") },
    { to: "/accounts", label: "Accounts", icon: Link2, active: path.startsWith("/accounts") },
    { to: "/workspace", label: "Settings", icon: Settings2, active: path.startsWith("/workspace") },
  ];

  return (
    <div className="app-shell">
      <aside className={menuOpen ? "sidebar open" : "sidebar"}>
        <div className="sidebar-top">
          <button className="brand-link" onClick={() => { navigate("/"); setMenuOpen(false); }} aria-label="Go home">
            <Logo />
          </button>
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(false)} aria-label="Close menu">
            <X size={20} />
          </button>
        </div>
        <nav className="side-nav">
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button
                key={item.to}
                className={item.active ? "active" : ""}
                onClick={() => {
                  navigate(item.to);
                  setMenuOpen(false);
                }}
              >
                <Icon size={18} /> {item.label}
              </button>
            );
          })}
        </nav>
        <div className="sidebar-card">
          <div className="mini-icon"><Sparkles size={16} /></div>
          <div>
            <strong>Create once</strong>
            <p>Repurpose everywhere. Pause any date — the campaign stays.</p>
          </div>
        </div>
        <div className="account-chip">
          <div className="avatar">
            {(user?.email || user?.user_metadata?.full_name || "C").slice(0, 1).toUpperCase()}
          </div>
          <div>
            <strong>{user?.user_metadata?.full_name || "Creator"}</strong>
            <span>{user?.email || "Signed in"}</span>
          </div>
          <button className="icon-button" onClick={() => auth.signOut()} title="Sign out" aria-label="Sign out">
            <LogOut size={17} />
          </button>
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(true)} aria-label="Open menu">
            <Menu size={21} />
          </button>
          <div className="mobile-brand"><Logo /></div>
          <div className="topbar-actions">
            <span className="status-pill"><span /> creatorOS</span>
            <button className="ghost-button" onClick={() => navigate("/workspace")} aria-label="Account">
              <span className="avatar tiny">{(user?.email || "C").slice(0, 1).toUpperCase()}</span>
            </button>
          </div>
        </header>

        <div className="workspace">
          {flow && (
            <div className="flow-stepper" aria-label="Campaign progress">
              {FLOW_STEPS.map((item, index) => {
                const isDone = index < activeIndex;
                const isActive = index === activeIndex;
                return (
                  <div
                    key={item.id}
                    className={`flow-step ${isDone ? "done" : ""} ${isActive ? "active" : ""}`}
                  >
                    <div className="flow-dot">{isDone ? <Check size={14} /> : index + 1}</div>
                    <span>{item.label}</span>
                    {index < FLOW_STEPS.length - 1 && <div className="flow-line" />}
                  </div>
                );
              })}
            </div>
          )}
          {children}
        </div>
      </main>
    </div>
  );
}

function PageHeading({ eyebrow, title, description, aside }) {
  return (
    <div className="page-heading">
      <div>
        {eyebrow && <div className="eyebrow">{eyebrow}</div>}
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {aside}
    </div>
  );
}

function Notice({ type = "info", children, onClose }) {
  return (
    <div className={`notice ${type}`}>
      {type === "success" ? <CheckCircle2 size={19} /> : <Sparkles size={19} />}
      <span>{children}</span>
      {onClose && <button onClick={onClose}><X size={16} /></button>}
    </div>
  );
}

async function copyText(text) {
  const value = String(text || "");
  if (!value) throw new Error("Nothing to copy");
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.left = "-9999px";
  document.body.appendChild(field);
  field.select();
  document.execCommand("copy");
  field.remove();
}

function CopyButton({ text, label = "Copy" }) {
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className="ghost-button copy-button"
      disabled={!text}
      onClick={async () => {
        try {
          await copyText(text);
          setDone(true);
          window.setTimeout(() => setDone(false), 1400);
        } catch {
          setDone(false);
        }
      }}
    >
      {done ? <Check size={14} /> : <Copy size={14} />}
      {done ? "Copied" : label}
    </button>
  );
}

function itemPostText(item) {
  if (item?.post_markdown) return item.post_markdown;
  const hook = item?.display_hook || item?.hook || "";
  const caption = item?.display_caption || item?.summary || "";
  return [hook && `## Hook\n${hook}`, caption && `## Caption\n${caption}`]
    .filter(Boolean)
    .join("\n\n");
}

const POST_STATUSES = [
  { id: "ai_generated", label: "AI generated", tone: "ai" },
  { id: "scheduled", label: "Scheduled", tone: "scheduled" },
  { id: "paused", label: "Needs review / paused", tone: "review" },
  { id: "posted", label: "Published", tone: "published" },
  { id: "skipped", label: "Won't post", tone: "failed" },
];

function normalizePostStatus(status) {
  const raw = String(status || "pending").toLowerCase().replace(/[\s'-]+/g, "_");
  if (["skipped", "wont_post", "cancelled", "canceled"].includes(raw)) return "skipped";
  if (["posted", "published"].includes(raw)) return "posted";
  if (["paused", "review", "needs_review", "needs_review_paused"].includes(raw)) return "paused";
  if (["ai_generated", "generated", "draft"].includes(raw)) return "ai_generated";
  return "scheduled";
}

function postStatusMeta(status) {
  const id = normalizePostStatus(status);
  return POST_STATUSES.find((row) => row.id === id) || POST_STATUSES[1];
}

function StatusSelect({ value, disabled, compact = false, onChange }) {
  const current = normalizePostStatus(value);
  const meta = postStatusMeta(current);
  return (
    <label className={`status-select ${compact ? "compact" : ""} is-${meta.tone}`}>
      {compact ? null : <span>Status</span>}
      <select
        aria-label="Post status"
        value={current}
        disabled={disabled}
        onChange={(event) => {
          const next = event.target.value;
          if (next !== current) onChange?.(next);
        }}
      >
        {POST_STATUSES.map((row) => (
          <option key={row.id} value={row.id}>{row.label}</option>
        ))}
      </select>
    </label>
  );
}

const CONNECT_PLATFORMS = ["youtube", "instagram", "linkedin", "twitter"];

function HomePage({ currentJob }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const [board, setBoard] = useState(null);

  useEffect(() => {
    creatorApi.board().then(setBoard).catch(() => setBoard({ items: [], summary: {} }));
  }, []);

  const items = board?.items || [];
  const summary = board?.summary || {};
  const hasCampaign = items.length > 0 || Boolean(currentJob);

  return (
    <AppShell flow={false}>
      <PageHeading
        eyebrow="Home"
        title={`${dayGreeting()}, ${displayName(auth.user)}`}
        description={
          hasCampaign
            ? "Your content this month — plan, edit, and schedule from here."
            : "Turn one video into a month of content. Create once. Repurpose everywhere."
        }
        aside={
          <button className="primary-button" onClick={() => navigate("/campaign")}>
            <Plus size={16} /> {hasCampaign ? "New campaign" : "Start a campaign"}
          </button>
        }
      />
      {hasCampaign ? (
        <>
          <div className="result-kpis">
            <div><Play size={19} /><span>Shorts</span><strong>{board?.video_renders ?? "—"}</strong></div>
            <div><Film size={19} /><span>Posts</span><strong>{summary.total_content_pieces || items.length || "—"}</strong></div>
            <div><CalendarDays size={19} /><span>Scheduled</span><strong>{board?.calendar?.total_posts || items.length || "—"}</strong></div>
            <div><Clock3 size={19} /><span>This run</span><strong>{summary.processing_human || "—"}</strong></div>
          </div>
          <div className="home-actions">
            <button className="home-card" onClick={() => navigate(currentJob ? `/results/${currentJob}` : "/results/latest")}>
              <Film size={18} />
              <strong>Open library</strong>
              <p>Review clips, captions, and downloads.</p>
            </button>
            <button className="home-card" onClick={() => navigate("/calendar")}>
              <CalendarDays size={18} />
              <strong>Content calendar</strong>
              <p>Pause a platform or any date.</p>
            </button>
            <button className="home-card" onClick={() => navigate("/accounts")}>
              <Link2 size={18} />
              <strong>Connected accounts</strong>
              <p>YouTube, Instagram, LinkedIn, and X.</p>
            </button>
          </div>
        </>
      ) : (
        <section className="panel home-empty">
          <span className="overline">Get started</span>
          <h2>One video. A month of content.</h2>
          <p>Upload a talk or podcast and creatorOS will plan, edit, and schedule across every platform.</p>
          <div className="home-actions">
            <button className="home-card" onClick={() => navigate("/campaign")}>
              <Upload size={18} />
              <strong>Upload a video</strong>
              <p>Paste a YouTube link or drop a file.</p>
            </button>
            <button className="home-card" onClick={() => navigate("/accounts")}>
              <Link2 size={18} />
              <strong>Connect accounts</strong>
              <p>Optional — you can generate without connecting.</p>
            </button>
            <button className="home-card" onClick={() => navigate("/calendar")}>
              <CalendarDays size={18} />
              <strong>See the calendar</strong>
              <p>Your month of posts will land here.</p>
            </button>
          </div>
        </section>
      )}
    </AppShell>
  );
}

function ConnectPage({ accounts, refreshAccounts, accountBusy }) {
  const navigate = useNavigate();
  const location = useLocation();
  const auth = useAuth();
  const [message, setMessage] = useState("");
  const [disconnecting, setDisconnecting] = useState("");
  const [showGuide, setShowGuide] = useState(() => {
    try {
      return sessionStorage.getItem("creatoros.fresh-session") === "1";
    } catch {
      return false;
    }
  });
  const closeGuide = (skipToCampaign = false) => {
    try {
      sessionStorage.removeItem("creatoros.fresh-session");
    } catch {
      /* ignore */
    }
    setShowGuide(false);
    if (skipToCampaign) navigate("/campaign");
  };
  const accountMap = useMemo(
    () => Object.fromEntries((accounts || []).map((account) => [account.platform, account])),
    [accounts],
  );
  const connectedCount = accounts.filter((item) => item.connected).length;

  useEffect(() => {
    const params = new URLSearchParams(location.search);
    for (const key of ["youtube", "instagram", "linkedin", "twitter"]) {
      const result = params.get(key);
      if (result === "connected") {
        const name = PLATFORM_META[key]?.name || key;
        setMessage(`${name} connected successfully.`);
        refreshAccounts();
        window.history.replaceState({}, "", window.location.pathname);
        break;
      }
      if (result === "denied") {
        const name = PLATFORM_META[key]?.name || key;
        setMessage(`${name} permission was not granted. You can try again whenever you are ready.`);
        window.history.replaceState({}, "", window.location.pathname);
        break;
      }
    }
  }, [location.search, refreshAccounts]);

  const connectAccount = (key) => {
    const name = PLATFORM_META[key]?.name || key;
    window.open(apiUrl(`/connect/${key}`), "_blank", "noopener,noreferrer");
    setMessage(`Finish ${name} authorization in the new tab, then return here.`);
  };

  const disconnectAccount = async (key) => {
    setDisconnecting(key);
    try {
      await creatorApi.disconnectAccount(key);
      setMessage(`${PLATFORM_META[key]?.name || key} disconnected from this workspace.`);
      await refreshAccounts();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setDisconnecting("");
    }
  };

  const connectCopy = {
    youtube: "Authorize CreatorOS to upload only the Shorts you approve.",
    instagram: "Connect Instagram to publish Reels you approve.",
    linkedin: "Connect LinkedIn to post the drafts you approve.",
    twitter: "Connect X to post threads you approve.",
  };

  return (
    <AppShell step="connect">
      {showGuide && (
        <NextStepGuide
          name={displayName(auth.user)}
          onStay={() => closeGuide(false)}
          onSkip={() => closeGuide(true)}
        />
      )}
      <PageHeading
        eyebrow="Accounts"
        title="Connect your publishing channels"
        description="This is step 1. Connect a channel, or skip and upload a video next."
        aside={<div className="linked-count"><strong>{connectedCount}</strong> of 4 linked</div>}
      />
      <section className="next-path">
        <div className="next-path-step current"><span>1</span> Connect accounts</div>
        <div className="next-path-line" />
        <div className="next-path-step"><span>2</span> Upload one video</div>
        <div className="next-path-line" />
        <div className="next-path-step"><span>3</span> Get a 30-day calendar</div>
      </section>

      {message && <Notice type={message.includes("success") ? "success" : "info"} onClose={() => setMessage("")}>{message}</Notice>}

      <div className="account-grid">
        {CONNECT_PLATFORMS.map((key) => {
          const meta = PLATFORM_META[key];
          const account = accountMap[key] || { connected: false, status: "not_connected" };
          const handle = account.display_name || account.username;
          return (
            <article className={`account-card ${account.connected ? "connected" : ""}`} key={key}>
              <div className="account-card-head">
                <div className={`platform-icon ${meta.tone}`}>
                  <BrandIcon platform={key} size={22} label={meta.name} />
                </div>
                <div>
                  <h3>{meta.name}</h3>
                  <p>{meta.detail}</p>
                </div>
                <span className={`connection-dot ${account.connected ? "on" : ""}`}>
                  {account.connected ? "Connected" : "Not connected"}
                </span>
              </div>
              <div className="account-card-body">
                {account.connected ? (
                  <>
                    <div className="connected-detail">
                      <CheckCircle2 size={18} />
                      <div>
                        <strong>{handle ? `Connected as ${handle}` : "Ready to publish"}</strong>
                        <span>Posts stay private or draft until you approve them</span>
                      </div>
                    </div>
                    <div className="card-actions">
                      <button className="secondary-button" onClick={() => connectAccount(key)}>
                        <RefreshCw size={16} /> Change account
                      </button>
                      <button className="danger-button" onClick={() => disconnectAccount(key)} disabled={disconnecting === key}>
                        {disconnecting === key ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}
                        Disconnect
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <p className="account-copy">{connectCopy[key]}</p>
                    <button className="primary-button compact" onClick={() => connectAccount(key)}>
                      <Link2 size={16} /> Connect {meta.name}
                    </button>
                  </>
                )}
              </div>
            </article>
          );
        })}
      </div>

      <div className="info-strip">
        <div><Sparkles size={18} /><span><strong>Optional step.</strong> You can generate and download a complete campaign without connecting an account.</span></div>
      </div>
      <div className="page-actions">
        <button className="primary-button" onClick={() => navigate("/campaign")}>
          Next: upload a video <ArrowRight size={17} />
        </button>
        <button className="text-button" onClick={() => navigate("/campaign")}>Skip for now</button>
        <button className="secondary-button push-right" onClick={refreshAccounts} disabled={accountBusy}>
          <RefreshCw className={accountBusy ? "spin" : ""} size={16} /> Refresh status
        </button>
      </div>
    </AppShell>
  );
}

function isYoutubeDownloadBlock(error) {
  const text = String(error || "").toLowerCase();
  return (
    text.includes("youtube blocked") ||
    text.includes("po token") ||
    text.includes("http error 403") ||
    text.includes("403 forbidden") ||
    text.includes("not a bot")
  );
}

function Field({ label, hint, children, wide }) {
  return (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}

function CampaignPage({ campaign, setCampaign }) {
  const navigate = useNavigate();
  const [uploading, setUploading] = useState(false);
  const [logoUploading, setLogoUploading] = useState(false);
  const [error, setError] = useState("");
  const update = (key, value) => setCampaign((current) => ({ ...current, [key]: value }));

  useEffect(() => {
    creatorApi.getBrand().then((brand) => {
      setCampaign((current) => ({
        ...current,
        brandName: current.brandName && current.brandName !== "CreatorOS"
          ? current.brandName
          : (brand.brand_name || current.brandName || ""),
        website: current.website || brand.website || "",
        hasLogo: Boolean(brand.has_logo),
        logoCache: Date.now(),
        tagline: current.tagline || brand.tagline || "",
        endScreenEnabled: Boolean(
          current.endScreenEnabled || brand.end_screen_enabled
        ),
        endScreenCta: current.endScreenCta || brand.end_screen_cta || "",
        endScreenTemplate: current.endScreenTemplate || brand.end_screen_template || "logo_name_website",
        endScreenDuration: current.endScreenDuration || brand.end_screen_duration || 3,
        onScreenCaptionsEnabled: current.onScreenCaptionsEnabled ?? brand.on_screen_captions_enabled !== false,
      }));
    }).catch(() => {});
  }, [setCampaign]);

  const handleFile = async (file) => {
    if (!file) return;
    setUploading(true);
    setError("");
    try {
      const result = await creatorApi.uploadSource(file);
      update("source", result.path);
      update("sourceName", file.name);
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setUploading(false);
    }
  };

  const handleLogo = async (file) => {
    if (!file) return;
    setLogoUploading(true);
    setError("");
    try {
      await creatorApi.uploadLogo(file);
      setCampaign((current) => ({
        ...current,
        hasLogo: true,
        logoCache: Date.now(),
        logoName: file.name,
      }));
    } catch (uploadError) {
      setError(uploadError.message);
    } finally {
      setLogoUploading(false);
    }
  };

  const handleClearLogo = async () => {
    try {
      await creatorApi.clearLogo();
      setCampaign((current) => ({ ...current, hasLogo: false, logoName: "", logoPreview: "" }));
    } catch (clearError) {
      setError(clearError.message);
    }
  };

  const continueNext = () => {
    if (!campaign.source.trim()) {
      setError(campaign.sourceType === "url" ? "Paste a YouTube or podcast URL to continue." : "Choose a video file to continue.");
      return;
    }
    if (campaign.endScreenEnabled && !String(campaign.brandName || "").trim()) {
      setError("Brand name is required for the end screen.");
      return;
    }
    setError("");
    navigate("/strategy");
  };

  return (
    <AppShell step="campaign">
      <PageHeading
        eyebrow="Content"
        title="Turn one video into a month of content"
        description="Upload your podcast and let creatorOS plan, edit, and schedule across every platform."
      />
      <section className="panel campaign-panel">
        <div className="source-switch">
          <button className={campaign.sourceType === "url" ? "active" : ""} onClick={() => update("sourceType", "url")}>
            <Link2 size={17} /> Podcast / YouTube URL
          </button>
          <button className={campaign.sourceType === "upload" ? "active" : ""} onClick={() => update("sourceType", "upload")}>
            <Upload size={17} /> Upload video
          </button>
        </div>

        {campaign.sourceType === "url" ? (
          <Field label="Podcast or YouTube URL" hint="Paste a public episode or video link. If YouTube blocks the download, switch to Upload video." wide>
            <div className="input-with-icon"><Link2 size={18} /><input value={campaign.source} onChange={(e) => update("source", e.target.value)} placeholder="https://youtube.com/watch?v=…" /></div>
          </Field>
        ) : (
          <Field label="Source video" hint="MP4, MOV, MKV, or WebM. Large files may take a moment to upload." wide>
            <label className={`upload-drop ${uploading ? "busy" : ""}`}>
              <FileVideo size={26} />
              <div>
                <strong>{campaign.sourceName || "Drop a video here or browse"}</strong>
                <span>{uploading ? "Uploading securely…" : "Your original is never modified"}</span>
              </div>
              {uploading ? <LoaderCircle className="spin" /> : <Upload size={19} />}
              <input type="file" accept="video/*,.mkv" onChange={(e) => handleFile(e.target.files?.[0])} />
            </label>
          </Field>
        )}

        <Field label="What kind of show is this?" hint="Comedy keeps the laugh. Interviews open on the bold line." wide>
        <div className="show-types">
          {SHOW_TYPES.map((item) => (
            <button
              type="button"
              key={item.id}
              className={(campaign.showType || "auto") === item.id ? "active" : ""}
              onClick={() => update("showType", item.id)}
            >
              <strong>{item.label}</strong>
              {item.detail ? <span>{item.detail}</span> : null}
            </button>
          ))}
        </div>
        </Field>

        <div className="form-grid">
          <Field label="Brand name">
            <input value={campaign.brandName} onChange={(e) => update("brandName", e.target.value)} placeholder="CreatorOS" />
          </Field>
          <Field label="Website" hint="Optional">
            <input value={campaign.website} onChange={(e) => update("website", e.target.value)} placeholder="https://yourbrand.com" />
          </Field>
          <Field label="Primary goal">
            <select value={campaign.goal} onChange={(e) => update("goal", e.target.value)}>
              <option>Brand awareness</option><option>Lead generation</option><option>Audience growth</option><option>Product education</option><option>Community engagement</option>
            </select>
          </Field>
          <Field label="Target audience" hint="Be specific enough to shape the writing.">
            <input value={campaign.audience} onChange={(e) => update("audience", e.target.value)} placeholder="Early-stage SaaS founders" />
          </Field>
          <Field label="Voice and tone">
            <select value={campaign.tone} onChange={(e) => update("tone", e.target.value)}>
              <option>Professional</option><option>Conversational</option><option>Bold</option><option>Educational</option><option>Playful</option>
            </select>
          </Field>
          <Field label="Campaign duration">
            <select value={campaign.durationDays} onChange={(e) => update("durationDays", Number(e.target.value))}>
              <option value={14}>14 days</option><option value={30}>30 days</option><option value={45}>45 days</option><option value={60}>60 days</option>
            </select>
          </Field>
          <Field label="Campaign start date">
            <input type="date" value={campaign.startDate} onChange={(e) => update("startDate", e.target.value)} />
          </Field>
        </div>
      </section>
      <section className="panel campaign-panel" style={{ marginTop: 18 }}>
        <div className="section-heading">
          <div>
            <span className="overline">Branding</span>
            <h2>End screen</h2>
          </div>
        </div>
        <BrandingFields
          value={{
            brandName: campaign.brandName,
            website: campaign.website,
            tagline: campaign.tagline || "",
            endScreenEnabled: Boolean(campaign.endScreenEnabled),
            endScreenDuration: campaign.endScreenDuration || 3,
            endScreenTemplate: campaign.endScreenTemplate || "logo_name_website",
            endScreenCta: campaign.endScreenCta || "",
            onScreenCaptionsEnabled: campaign.onScreenCaptionsEnabled !== false,
            hasLogo: Boolean(campaign.hasLogo),
            logoCache: campaign.logoCache,
            logoName: campaign.logoName,
            logoPreview: campaign.logoPreview,
          }}
          onChange={(next) => setCampaign((current) => ({
            ...current,
            brandName: next.brandName,
            website: next.website,
            tagline: next.tagline,
            endScreenEnabled: next.endScreenEnabled,
            endScreenDuration: next.endScreenDuration,
            endScreenTemplate: next.endScreenTemplate,
            endScreenCta: next.endScreenCta,
            onScreenCaptionsEnabled: next.onScreenCaptionsEnabled,
            hasLogo: next.hasLogo,
            logoCache: next.logoCache,
            logoName: next.logoName,
            logoPreview: next.logoPreview,
          }))}
          logoUploading={logoUploading}
          onLogoUpload={handleLogo}
          onClearLogo={handleClearLogo}
          compact
        />
      </section>
      {error && <Notice>{error}</Notice>}
      <div className="page-actions">
        <button className="secondary-button" onClick={() => navigate("/")}><ArrowLeft size={17} /> Back</button>
        <button className="primary-button" onClick={continueNext}>Build my content plan <ArrowRight size={17} /></button>
      </div>
    </AppShell>
  );
}

function Counter({ value, onChange, min = 0, max = 30 }) {
  return (
    <div className="counter">
      <button onClick={() => onChange(Math.max(min, value - 1))}>−</button>
      <strong>{value}</strong>
      <button onClick={() => onChange(Math.min(max, value + 1))}>+</button>
    </div>
  );
}

function StrategyPage({ campaign, plan, setPlan, onGenerate, generating }) {
  const navigate = useNavigate();
  const platformNames = {
    instagram_reels: "Instagram Reels",
    youtube_shorts: "YouTube Shorts",
    linkedin: "LinkedIn",
    twitter: "X",
  };
  const totals = Object.values(plan).filter((item) => item.enabled).reduce((sum, item) => sum + item.count, 0);
  const update = (key, patch) => setPlan((current) => ({ ...current, [key]: { ...current[key], ...patch } }));

  return (
    <AppShell step="strategy">
      <PageHeading
        eyebrow="Content strategy"
        title="Shape the month before AI starts"
        description="Tune how many posts each platform gets. Pause a channel later without deleting the campaign."
      />
      <div className="strategy-layout">
        <div className="strategy-grid">
          {Object.entries(plan).map(([key, item]) => {
            const name = platformNames[key];
            return (
              <article className={`strategy-card ${item.enabled ? "" : "disabled"}`} key={key}>
                <div className="strategy-head">
                  <div className="platform-icon purple">
                    <BrandIcon platform={key} size={22} label={name} />
                  </div>
                  <div><h3>{name}</h3><p>{item.suggested}</p></div>
                  <button className={`toggle ${item.enabled ? "on" : ""}`} onClick={() => update(key, { enabled: !item.enabled })} aria-label={`${item.enabled ? "Disable" : "Enable"} ${name}`}><span /></button>
                </div>
                <div className="strategy-controls">
                  <Field label="Assets"><Counter value={item.count} onChange={(count) => update(key, { count })} /></Field>
                  <Field label="Post every"><div className="interval-control"><Counter value={item.interval_days} min={1} max={14} onChange={(interval_days) => update(key, { interval_days })} /><span>days</span></div></Field>
                </div>
                <Field label="Purpose"><input value={item.purpose} onChange={(e) => update(key, { purpose: e.target.value })} /></Field>
                <div className="strategy-foot"><span>Audience</span><strong>{campaign.audience || "Your audience"}</strong></div>
              </article>
            );
          })}
        </div>
        <aside className="summary-card">
          <div className="summary-title"><Sparkles size={19} /><span>Campaign snapshot</span></div>
          <div className="summary-duration"><span>Duration</span><strong>{campaign.durationDays} days</strong></div>
          <div className="summary-list">
            {Object.entries(plan).filter(([, item]) => item.enabled).map(([key, item]) => (
              <div key={key}><span>{platformNames[key]}</span><strong>{item.count}</strong></div>
            ))}
          </div>
          <div className="summary-total"><span>Total content pieces</span><strong>{totals}</strong></div>
          <div className="estimate-grid">
            <div><Clock3 size={16} /><span>Estimated processing</span><strong>8–15 min</strong></div>
            <div><Film size={16} /><span>Distinct video edits</span><strong>{(plan.youtube_shorts.enabled ? plan.youtube_shorts.count : 0) + (plan.instagram_reels.enabled ? plan.instagram_reels.count : 0)}</strong></div>
          </div>
          <button className="primary-button full" onClick={onGenerate} disabled={generating || !campaign.source}>
            {generating ? <LoaderCircle className="spin" size={18} /> : <Rocket size={18} />}
            {generating ? "Starting campaign…" : "Generate AI campaign"}
          </button>
          <p className="privacy-note">You stay in control. CreatorOS prepares drafts and private uploads only.</p>
        </aside>
      </div>
      <div className="page-actions">
        <button className="secondary-button" onClick={() => navigate("/campaign")}><ArrowLeft size={17} /> Back</button>
      </div>
    </AppShell>
  );
}

function formatRemaining(status) {
  const elapsed = status?.elapsed_seconds || 0;
  const step = status?.step;
  const scan = status?.scan_progress || {};
  const typical = {
    video: 90,
    transcript: 240,
    highlight: 20,
    strategy: 40,
    ranking: 20,
    editing: 360,
    routing: 20,
    marketing: 90,
    planning: 40,
    packaging: 40,
  };
  const order = Object.keys(typical);
  const idx = Math.max(0, order.indexOf(step));
  let leftover = 0;
  if (step === "transcript" && scan.max_scan_seconds) {
    const heard = Number(scan.scanned_seconds) || 0;
    const cap = Number(scan.max_scan_seconds) || 180;
    leftover += Math.max(30, ((cap - heard) / cap) * typical.transcript);
  } else {
    leftover += typical[step] || 60;
  }
  for (let i = idx + 1; i < order.length; i += 1) leftover += typical[order[i]];
  leftover = Math.max(30, leftover - Math.min(elapsed * 0.05, 30));
  if (leftover < 60) return "Less than a minute";
  return `About ${Math.ceil(leftover / 60)} min`;
}

function shiftYearMonth(year, month, delta) {
  const next = new Date(year, month - 1 + delta, 1);
  return { year: next.getFullYear(), month: next.getMonth() + 1 };
}

function CalendarMonth({ calendar, holds = {}, onHold, onResume, onPause, onResumeItem, onSkip, onStatus, onSelect }) {
  const [selected, setSelected] = useState(null);
  const [view, setView] = useState(calendar);
  const [monthBusy, setMonthBusy] = useState(false);
  useEffect(() => {
    setView((prev) => {
      if (
        prev?.year &&
        prev?.month &&
        calendar?.year &&
        calendar?.month &&
        (prev.year !== calendar.year || prev.month !== calendar.month)
      ) {
        return prev;
      }
      return calendar;
    });
  }, [calendar]);
  const shown = view || calendar;
  if (!shown?.cells?.length) return null;
  const chosen = shown.cells.find((cell) => cell.date === selected) || null;
  const legend = shown.legend || Object.entries(CALENDAR_PLATFORMS).map(([id, meta]) => ({ id, ...meta }));
  const stayOnMonth = async () => {
    if (!shown.year || !shown.month) return;
    try {
      const data = await creatorApi.calendar(shown.year, shown.month);
      setView(data.calendar);
    } catch (err) {
      console.warn(err);
    }
  };
  const goMonth = async (delta) => {
    if (!shown.year || !shown.month) return;
    const next = shiftYearMonth(shown.year, shown.month, delta);
    setMonthBusy(true);
    try {
      const data = await creatorApi.calendar(next.year, next.month);
      setView(data.calendar);
      setSelected(null);
    } catch (err) {
      console.warn(err);
    } finally {
      setMonthBusy(false);
    }
  };
  const runStay = async (fn) => {
    setMonthBusy(true);
    try {
      await fn?.(shown.year, shown.month);
      await stayOnMonth();
    } finally {
      setMonthBusy(false);
    }
  };

  return (
    <section className="panel calendar-panel" id="calendar">
      <div className="section-heading">
        <div>
          <span className="overline">Content calendar</span>
          <div className="calendar-month-nav">
            <button type="button" className="icon-button" onClick={() => goMonth(-1)} disabled={monthBusy} aria-label="Previous month">
              <ArrowLeft size={16} />
            </button>
            <h2>{shown.label}</h2>
            <button type="button" className="icon-button" onClick={() => goMonth(1)} disabled={monthBusy} aria-label="Next month">
              <ArrowRight size={16} />
            </button>
          </div>
        </div>
        <span>{shown.blocked_days} days booked · {shown.total_posts} posts{monthBusy ? " · loading" : ""}</span>
      </div>
      <div className="calendar-legend">
        {legend.map((item) => {
          const held = Boolean(holds[item.id]);
          return (
            <button
              type="button"
              className={`cal-chip ${held ? "held" : ""}`}
              key={item.id || item.short}
              onClick={() => runStay((year, month) => (held ? onResume?.(item.id, year, month) : onHold?.(item.id, year, month)))}
              title={held ? `Resume every ${item.label} date` : `Pause every ${item.label} date — any month`}
            >
              <BrandIcon platform={item.id} size={16} label={item.label} />
              {item.label}
              <em>{held ? "paused" : "live"}</em>
            </button>
          );
        })}
      </div>
      <p className="calendar-hint">Open any month. Tap a platform to pause every date, or change a post’s status in the library or on a day — schedule it, hold it, or mark it as won’t post.</p>
      <div className="calendar-legend status-legend">
        <span className="cal-status is-ai">AI generated</span>
        <span className="cal-status is-scheduled">Scheduled</span>
        <span className="cal-status is-review">Needs review / paused</span>
        <span className="cal-status is-published">Published</span>
        <span className="cal-status is-failed">Won't post</span>
      </div>
      <div className="calendar-weekdays">
        {(shown.weekdays || ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]).map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="calendar-grid">
        {shown.cells.map((cell, index) => (
          <button
            type="button"
            key={cell.date || `empty-${index}`}
            className={`calendar-day ${cell.in_month ? "" : "empty"} ${cell.blocked ? "blocked" : ""} ${cell.today ? "today" : ""} ${selected === cell.date ? "selected" : ""}`}
            disabled={!cell.in_month}
            onClick={() => {
              setSelected(cell.date);
              onSelect?.(cell);
            }}
          >
            <strong>{cell.day || ""}</strong>
            {Boolean(cell.items?.length) && (
              <div className="calendar-markers">
                {cell.items.slice(0, 4).map((row, markerIndex) => {
                  const marker = row.marker || {};
                  const meta = postStatusMeta(row.status);
                  const dimmed = holds[marker.id] || meta.id === "paused" || meta.id === "skipped";
                  return (
                    <span
                      className={`cal-dot ${dimmed ? "held" : ""} is-${meta.tone}`}
                      key={`${cell.date}-${row.id || marker.id}-${markerIndex}`}
                      title={`${marker.label}: ${meta.label}`}
                    >
                      <BrandIcon platform={marker.id} size={18} label={marker.label} />
                    </span>
                  );
                })}
              </div>
            )}
          </button>
        ))}
      </div>
      {chosen?.items?.length > 0 && (
        <div className="calendar-day-detail">
          <strong>{chosen.date}</strong>
          {chosen.items.map((item) => {
            const meta = postStatusMeta(item.status);
            const held = meta.id === "paused" || meta.id === "skipped";
            return (
              <div key={item.id}>
                <span className={`cal-chip ${held ? "held" : ""}`}>
                  <BrandIcon platform={item.marker?.id || item.platform} size={16} label={item.marker?.label} />
                  {item.marker?.label}
                </span>
                <em>{item.hook || "Scheduled post"}</em>
                {onStatus ? (
                  <StatusSelect
                    compact
                    value={item.status}
                    disabled={monthBusy}
                    onChange={(status) => runStay((year, month) => onStatus(item.id, status, year, month))}
                  />
                ) : (
                  <>
                    <span className={`cal-status is-${meta.tone}`}>{meta.label}</span>
                    {meta.id !== "posted" && (
                      <div className="calendar-day-actions">
                        {held && meta.id === "paused" ? (
                          <button type="button" className="text-button" onClick={() => runStay((year, month) => onResumeItem?.(item.id, year, month))}>
                            Resume
                          </button>
                        ) : meta.id !== "skipped" ? (
                          <button type="button" className="text-button" onClick={() => runStay((year, month) => onPause?.(item.id, year, month))}>
                            Pause
                          </button>
                        ) : null}
                        {meta.id !== "skipped" && onSkip && (
                          <button type="button" className="text-button" onClick={() => runStay((year, month) => onSkip(item.id, year, month))}>
                            Skip
                          </button>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

function ProcessingPage({ currentJob, onComplete, plan, setPlan }) {
  const { jobId: paramJobId } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const jobId = paramJobId || currentJob;
  const stayOnProgress =
    new URLSearchParams(location.search).get("view") === "progress";
  const [status, setStatus] = useState(null);
  const [pollError, setPollError] = useState("");
  const [stopping, setStopping] = useState(false);
  const [stopNote, setStopNote] = useState("");
  const planPlatforms = Object.keys(plan || DEFAULT_PLAN);
  const [stopPlatform, setStopPlatform] = useState(() => {
    const first = Object.entries(plan || DEFAULT_PLAN).find(([, item]) => item?.enabled && (item?.count || 0) > 0);
    return first?.[0] || "instagram_reels";
  });
  const [stoppedPlatforms, setStoppedPlatforms] = useState(() =>
    Object.entries(plan || {})
      .filter(([, item]) => !item?.enabled || (item?.count || 0) <= 0)
      .map(([key]) => key),
  );

  useEffect(() => {
    if (!jobId) return undefined;
    let active = true;
    let timer;
    const poll = async () => {
      try {
        const next = await creatorApi.status(jobId);
        if (!active) return;
        setStatus(next);
        setPollError("");
        if (next.status === "completed" || next.status === "stopped") {
          onComplete?.(jobId);
          if (!stayOnProgress) {
            timer = setTimeout(() => navigate(`/complete/${jobId}`), 900);
          }
        } else if (next.status !== "failed") {
          timer = setTimeout(poll, 2000);
        }
      } catch (error) {
        if (!active) return;
        setPollError(error.message);
        timer = setTimeout(poll, 4000);
      }
    };
    poll();
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [jobId, navigate, onComplete, stayOnProgress]);

  const live = status?.status === "running" || status?.status === "stopping" || status?.status === "queued";
  const finished = status?.status === "completed" || status?.status === "stopped";
  const scan = status?.scan_progress || {};

  const stopOnePlatform = async () => {
    if (!jobId || !stopPlatform) return;
    const label = PLAN_PLATFORM_LABELS[stopPlatform] || stopPlatform.replaceAll("_", " ");
    setStopping(true);
    try {
      await creatorApi.reduceScope(jobId, { [stopPlatform]: { count: 0, enabled: false } });
      setStoppedPlatforms((current) => (current.includes(stopPlatform) ? current : [...current, stopPlatform]));
      setStopNote(`Stopped ${label}. creatorOS will keep going on the other platforms.`);
      if (setPlan && plan?.[stopPlatform]) {
        setPlan({
          ...plan,
          [stopPlatform]: { ...plan[stopPlatform], count: 0, enabled: false },
        });
      }
      const nextLive = planPlatforms.find(
        (key) => key !== stopPlatform && !stoppedPlatforms.includes(key) && (plan?.[key]?.count || 0) > 0,
      );
      if (nextLive) setStopPlatform(nextLive);
    } catch (error) {
      setStopNote(error.message);
    } finally {
      setStopping(false);
    }
  };

  const stopRun = async (mode) => {
    if (!jobId) return;
    setStopping(true);
    try {
      const result = await creatorApi.stopJob(jobId, { mode });
      setStopNote(result.message || "Stop requested.");
    } catch (error) {
      setStopNote(error.message);
    } finally {
      setStopping(false);
    }
  };

  if (!jobId) return <Navigate to="/strategy" replace />;

  const progress = status?.progress_percent || 0;
  const backendSteps = status?.steps || [];
  const activeStep = PROCESSING_STEPS[Math.max((status?.step_index || 1) - 1, 0)];
  const youtubeBlocked = isYoutubeDownloadBlock(status?.error);

  return (
    <AppShell step="processing">
      <PageHeading
        eyebrow="AI agent"
        title={
          status?.status === "stopped"
            ? "Campaign stopped early"
            : status?.status === "completed"
              ? "Your campaign is ready"
              : status?.status === "stopping"
                ? "Winding this campaign down"
                : "creatorOS is thinking"
        }
        description={
          status?.status === "stopped"
            ? status.message || "CreatorOS kept whatever it already finished and skipped the rest."
            : status?.status === "completed"
              ? "Every asset has been edited, written, scheduled, and packaged."
              : "Leave this open, stop one platform, or stop the whole run after this step."
        }
        aside={
          <div className="heading-actions">
            {stayOnProgress && finished && (
              <button
                className="secondary-button"
                onClick={() => navigate(`/complete/${jobId}`)}
              >
                <ArrowLeft size={16} /> Back to summary
              </button>
            )}
            <div className="live-badge">
              <span /> {finished ? (status?.status === "stopped" ? "Stopped" : "Completed") : status?.status === "stopping" ? "Stopping" : "Live processing"}
            </div>
          </div>
        }
      />
      <section className="processing-hero">
        <div className="progress-summary">
          <div className="progress-ring" style={{ "--progress": `${progress * 3.6}deg` }}>
            <div><strong>{progress}%</strong><span>complete</span></div>
          </div>
          <div className="progress-copy">
            <div className="processing-brand">
              <BrandMark size={36} />
              <span className="overline">creatorOS is thinking</span>
            </div>
            <h2>
              {status?.status === "failed"
                ? youtubeBlocked
                  ? "YouTube blocked the download"
                  : "This run stopped"
                : status?.step_label || activeStep?.label || "Analyzing your podcast"}
            </h2>
            <p>
              {status?.status === "failed"
                ? youtubeBlocked
                  ? "This is YouTube anti-bot, not a bad URL. Try Again — paste-a-link does not require a signed-in browser. Upload the MP4 if YouTube keeps blocking this network."
                  : status?.error || "The campaign stopped unexpectedly."
                : activeStep?.description || "Identifying moments, then building your month of content."}
            </p>
            <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
            <div className="progress-meta">
              <span><Clock3 size={15} /> Elapsed: {status?.elapsed_human || "0s"}</span>
              <span><Zap size={15} /> Remaining: {live ? formatRemaining(status) : "Done"}</span>
            </div>
          </div>
        </div>
        {status?.status === "failed" && <Notice>{status.error || "The campaign stopped unexpectedly."}</Notice>}
        {status?.status === "failed" && (
          <div className="page-actions" style={{ marginTop: 4 }}>
            <button
              className="primary-button"
              onClick={() => navigate("/campaign")}
            >
              <Upload size={16} /> Upload the video file instead
            </button>
          </div>
        )}
        {status?.status === "stopped" && <Notice>{status.message || "The run was stopped. Anything already cut is in the campaign library."}</Notice>}
        {stopNote && <Notice>{stopNote}</Notice>}
        {pollError && <Notice>Connection interrupted: {pollError}. Retrying automatically…</Notice>}
      </section>

      <div className="processing-layout">
        <section className="panel timeline-panel">
          <div className="section-heading"><div><span className="overline">AI agent</span><h2>What creatorOS is doing</h2></div><span>{backendSteps.filter((s) => s.status === "done").length} / 9 complete</span></div>
          <div className="process-timeline">
            {PROCESSING_STEPS.map((item, index) => {
              const backend = backendSteps[index] || {};
              const state = backend.status || (index === 0 ? "active" : "pending");
              return (
                <div className={`timeline-item ${state}`} key={item.id}>
                  <div className="timeline-marker">
                    {state === "done" ? <Check size={16} /> : state === "active" ? <LoaderCircle className="spin" size={17} /> : index + 1}
                  </div>
                  <div className="timeline-copy"><strong>{item.label}</strong><span>{item.description}</span></div>
                  <div className="timeline-state">
                    {state === "done" ? "Done" : state === "active" ? "In progress" : state === "error" ? "Needs attention" : state === "skipped" ? "Skipped" : "Waiting"}
                  </div>
                </div>
              );
            })}
          </div>
        </section>
        <aside className="processing-side">
          {live && (
            <div className="panel compact-panel stop-panel">
              <div className="summary-title"><Ban size={18} /><span>Stop a platform</span></div>
              <p>Choose a channel, then stop it. The rest of the campaign keeps running.</p>
              <label className="field">
                <span>Platform</span>
                <select value={stopPlatform} onChange={(e) => setStopPlatform(e.target.value)}>
                  {planPlatforms.map((key) => {
                    const stopped = stoppedPlatforms.includes(key);
                    return (
                      <option key={key} value={key} disabled={stopped}>
                        {(PLAN_PLATFORM_LABELS[key] || key.replaceAll("_", " "))}{stopped ? " — stopped" : ""}
                      </option>
                    );
                  })}
                </select>
              </label>
              <button
                className="secondary-button full"
                disabled={stopping || stoppedPlatforms.includes(stopPlatform)}
                onClick={stopOnePlatform}
              >
                {stopping ? <LoaderCircle className="spin" size={16} /> : <Square size={16} />} Stop this platform
              </button>
              {stoppedPlatforms.length > 0 && (
                <p className="stopped-list">
                  Stopped: {stoppedPlatforms.map((key) => PLAN_PLATFORM_LABELS[key] || key).join(", ")}
                </p>
              )}
              <button className="danger-button full" disabled={stopping} onClick={() => stopRun("finish_current")}>
                {stopping ? <LoaderCircle className="spin" size={16} /> : <Ban size={16} />} Stop entire run
              </button>
            </div>
          )}
          <div className="panel compact-panel">
            <div className="summary-title"><Sparkles size={18} /><span>Progress so far</span></div>
            <ul className="check-list">
              <li><CheckCircle2 size={16} /> Identified interesting moments</li>
              <li><CheckCircle2 size={16} /> Finding potential Shorts</li>
              <li><CheckCircle2 size={16} /> Detecting educational segments</li>
              <li><CheckCircle2 size={16} /> Building your 30-day content strategy</li>
            </ul>
          </div>
          <div className="panel compact-panel reassurance">
            <Sparkles size={20} />
            <h3>Safe to step away</h3>
            <p>Your job continues on the backend. Return with this campaign link anytime.</p>
            <button className="secondary-button full" onClick={() => navigator.clipboard?.writeText(window.location.href)}>
              <Link2 size={16} /> Copy campaign link
            </button>
          </div>
        </aside>
      </div>
    </AppShell>
  );
}

function CompletionPage({ currentJob }) {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const resolvedJob = jobId || currentJob;
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");
  const [holds, setHolds] = useState({});

  const loadBoard = () =>
    creatorApi.board().then((data) => {
      setBoard(data);
      setHolds(data.holds || data.calendar?.holds || {});
    }).catch((err) => setError(err.message));

  useEffect(() => {
    loadBoard();
  }, []);

  const applyHold = async (platform, resume = false, year, month) => {
    try {
      resume
        ? await creatorApi.resumePlatform(platform, year, month)
        : await creatorApi.holdPlatform(platform, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const skipItem = async (itemId, year, month) => {
    try {
      await creatorApi.skipPost(itemId, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const pauseItem = async (itemId, year, month) => {
    try {
      await creatorApi.pausePost(itemId, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const resumeItem = async (itemId, year, month) => {
    try {
      await creatorApi.resumePost(itemId, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const setItemStatus = async (itemId, status, year, month) => {
    try {
      const data = await creatorApi.setPostStatus(itemId, status, year, month);
      setBoard((prev) => ({
        ...(prev || {}),
        items: (prev?.items || []).map((item) =>
          item.id === itemId ? { ...item, status: data.status || status } : item
        ),
        calendar: data.calendar || prev?.calendar,
        holds: data.holds || prev?.holds,
      }));
      setHolds(data.holds || {});
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };

  const items = board?.items || [];
  const summary = board?.summary || {};
  const platformCounts = items.reduce((counts, item) => {
    const platform = item.assigned_platform || "other";
    counts[platform] = (counts[platform] || 0) + 1;
    return counts;
  }, {});

  return (
    <AppShell flow={false}>
      <section className="completion-hero">
        <div className="completion-burst"><Check size={34} /></div>
        <div>
          <div className="eyebrow">Campaign complete</div>
          <h1>Your content engine is ready</h1>
          <p>
            Everything is generated and dated. Pause a platform or a single date
            any time this month — the rest of the campaign keeps moving.
          </p>
        </div>
        <div className="completion-actions">
          <button className="primary-button" onClick={() => navigate(`/results/${resolvedJob}`)}>
            Open campaign library <ArrowRight size={17} />
          </button>
          <button className="secondary-button" onClick={() => navigate("/calendar")}>
            <CalendarDays size={16} /> Manage posting
          </button>
          {resolvedJob && (
            <a className="secondary-button" href={apiUrl(`/download-campaign/${resolvedJob}`)}>
              <Download size={16} /> Download package
            </a>
          )}
        </div>
      </section>

      {error && <Notice>{error}</Notice>}

      <CalendarMonth
        calendar={board?.calendar}
        holds={holds}
        onHold={(platform, year, month) => applyHold(platform, false, year, month)}
        onResume={(platform, year, month) => applyHold(platform, true, year, month)}
        onPause={pauseItem}
        onResumeItem={resumeItem}
        onSkip={skipItem}
        onStatus={setItemStatus}
      />

      <div className="completion-kpis">
        <div className="completion-kpi">
          <div className="kpi-icon"><Sparkles size={20} /></div>
          <span>Content pieces</span>
          <strong>{summary.total_content_pieces || items.length || "—"}</strong>
          <small>Ready for review</small>
        </div>
        <div className="completion-kpi">
          <div className="kpi-icon"><Film size={20} /></div>
          <span>Distinct video edits</span>
          <strong>{board?.video_renders ?? "—"}</strong>
          <small>Shorts and Reels</small>
        </div>
        <div className="completion-kpi">
          <div className="kpi-icon"><Clock3 size={20} /></div>
          <span>Processing time</span>
          <strong>{summary.processing_human || "—"}</strong>
          <small>End-to-end</small>
        </div>
        <div className="completion-kpi">
          <div className="kpi-icon"><CalendarDays size={20} /></div>
          <span>On the calendar</span>
          <strong>{board?.calendar?.total_posts || items.length || "—"}</strong>
          <small>Pause any platform anytime</small>
        </div>
      </div>

      <div className="completion-layout">
        <section className="panel completion-panel">
          <div className="section-heading">
            <div>
              <span className="overline">Delivery summary</span>
              <h2>Everything CreatorOS completed</h2>
            </div>
            <span>100% complete</span>
          </div>
          <div className="delivery-list">
            {[
              ["Source analyzed", "Audio, words, movement, scenes, and loud beats checked together"],
              ["Moments selected", "Hooks ranked for clarity, emotion, novelty, and visual energy"],
              ["Video edits directed", "Cuts, punch-ins, captions, and platform openings prepared"],
              ["Platform copy written", "Titles, captions, hashtags, angles, and CTAs rewritten per channel"],
              ["Calendar planned", "Every approved asset assigned a campaign date"],
              ["Campaign packaged", "Final videos, copy, strategy, and schedule added to the download"],
            ].map(([title, description]) => (
              <div className="delivery-item" key={title}>
                <div><Check size={15} /></div>
                <span><strong>{title}</strong><small>{description}</small></span>
              </div>
            ))}
          </div>
        </section>

        <aside className="completion-side">
          <section className="panel completion-panel platform-delivery">
            <div className="summary-title"><BarChart3 size={18} /><span>Platform delivery</span></div>
            <div className="platform-delivery-list">
              {Object.keys(platformCounts).length ? (
                Object.entries(platformCounts).map(([platform, count]) => (
                  <div key={platform}>
                    <span>{platform.replaceAll("_", " ")}</span>
                    <strong>{count}</strong>
                  </div>
                ))
              ) : (
                <p>Loading platform totals…</p>
              )}
            </div>
          </section>

          <section className="panel completion-panel editor-efficiency">
            <div className="summary-title"><Pause size={18} /><span>Posting control</span></div>
            <strong>{Object.values(holds).filter(Boolean).length} platforms paused</strong>
            <p>
              Generated clips stay in the library. Pause a channel or any date
              — turn it back on whenever you want.
            </p>
          </section>
        </aside>
      </div>

      <section className="next-step-card">
        <div>
          <span className="overline">What happens next</span>
          <h2>Review, approve, then publish</h2>
          <p>
            Campaign Library contains every video and post. Nothing publishes
            until you approve it.
          </p>
        </div>
        <div>
          <button className="primary-button" onClick={() => navigate(`/results/${resolvedJob}`)}>
            Review all assets <ArrowRight size={17} />
          </button>
          <button className="secondary-button" onClick={() => navigate("/campaign")}>
            <Plus size={16} /> Create another campaign
          </button>
        </div>
      </section>
    </AppShell>
  );
}

function ResultsPage({ currentJob }) {
  const { jobId } = useParams();
  const navigate = useNavigate();
  const resolvedJob = jobId === "latest" ? currentJob : jobId;
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");
  const [activePlatform, setActivePlatform] = useState("all");
  const [deckPlatform, setDeckPlatform] = useState("");
  const [holds, setHolds] = useState({});
  const [statusBusy, setStatusBusy] = useState("");

  const loadBoard = () =>
    creatorApi.board().then((data) => {
      setBoard(data);
      setHolds(data.holds || data.calendar?.holds || {});
    }).catch((err) => setError(err.message));

  useEffect(() => {
    loadBoard();
  }, []);

  const applyHold = async (platform, resume = false, year, month) => {
    try {
      resume
        ? await creatorApi.resumePlatform(platform, year, month)
        : await creatorApi.holdPlatform(platform, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const skipItem = async (itemId, year, month) => {
    try {
      await creatorApi.skipPost(itemId, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const pauseItem = async (itemId, year, month) => {
    try {
      await creatorApi.pausePost(itemId, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const resumeItem = async (itemId, year, month) => {
    try {
      await creatorApi.resumePost(itemId, year, month);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    }
  };
  const setItemStatus = async (itemId, status, year, month) => {
    setStatusBusy(itemId);
    try {
      const data = await creatorApi.setPostStatus(itemId, status, year, month);
      setBoard((prev) => ({
        ...(prev || {}),
        items: (prev?.items || []).map((item) =>
          item.id === itemId ? { ...item, status: data.status || status } : item
        ),
        calendar: data.calendar || prev?.calendar,
        holds: data.holds || prev?.holds,
      }));
      setHolds(data.holds || {});
      await loadBoard();
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setStatusBusy("");
    }
  };

  const items = board?.items || [];
  const platforms = [...new Set(items.map((item) => item.assigned_platform).filter(Boolean))];
  const visible = activePlatform === "all" ? items : items.filter((item) => item.assigned_platform === activePlatform);
  const summary = board?.summary || {};
  const decks = board?.campaign_posts || {};
  const deckKeys = Object.keys(decks);
  const currentDeck = deckKeys.includes(deckPlatform) ? deckPlatform : deckKeys[0];

  return (
    <AppShell flow={false}>
      <PageHeading
        eyebrow="Library"
        title="Your campaign assets"
        description="Preview the 9:16 cuts, copy the markdown, and set each post to scheduled, paused, or won’t post."
        aside={
          <div className="heading-actions">
            <button
              className="secondary-button"
              onClick={() =>
                resolvedJob
                  ? navigate(`/complete/${resolvedJob}`)
                  : navigate(-1)
              }
            >
              <ArrowLeft size={16} /> Back to summary
            </button>
            {resolvedJob && (
              <a
                className="primary-button"
                href={apiUrl(`/download-campaign/${resolvedJob}`)}
              >
                <Download size={17} /> Download campaign
              </a>
            )}
          </div>
        }
      />
      {error && <Notice>{error}</Notice>}
      <div className="result-kpis">
        <div><Play size={19} /><span>Shorts</span><strong>{board?.video_renders ?? "—"}</strong></div>
        <div><Film size={19} /><span>Posts</span><strong>{summary.total_content_pieces || items.length || "—"}</strong></div>
        <div><CalendarDays size={19} /><span>Scheduled</span><strong>{board?.calendar?.total_posts || items.length || "—"}</strong></div>
        <div><Clock3 size={19} /><span>This run</span><strong>{summary.processing_human || "—"}</strong></div>
      </div>
      <div className="result-toolbar">
        <div className="platform-tabs">
          <button className={activePlatform === "all" ? "active" : ""} onClick={() => setActivePlatform("all")}>All <span>{items.length}</span></button>
          {platforms.map((platform) => <button key={platform} className={activePlatform === platform ? "active" : ""} onClick={() => setActivePlatform(platform)}>{platform.replaceAll("_", " ")} <span>{items.filter((i) => i.assigned_platform === platform).length}</span></button>)}
        </div>
        <button className="secondary-button" onClick={() => navigate("/campaign")}><Plus size={16} /> New campaign</button>
      </div>
      {!board ? (
        <div className="loading-state"><LoaderCircle className="spin" /><span>Loading campaign assets…</span></div>
      ) : (
        <>
          <div className="library-status-intro">
            <p className="asset-copy-hint">
              Same statuses as the calendar. On each clip, choose whether it should actually post, wait, or not go out.
            </p>
            <div className="calendar-legend status-legend">
              {POST_STATUSES.map((row) => (
                <span className={`cal-status is-${row.tone}`} key={row.id}>{row.label}</span>
              ))}
            </div>
          </div>
          <div className="asset-grid">
          {visible.map((item, index) => (
            <article className="asset-card" key={item.id || `${item.assigned_platform}-${index}`}>
              <div className="asset-card-top">
                <div className="asset-meta">
                  <span>{item.package_label || "Platform cut"}</span>
                  <span>{item.scheduled_date || "Queued"}</span>
                </div>
                <div className="asset-status-row">
                  <StatusSelect
                    value={item.status}
                    disabled={!item.id || statusBusy === item.id}
                    onChange={(status) => setItemStatus(item.id, status)}
                  />
                </div>
              </div>
              {item.play_url ? (
                <div className="asset-video">
                  <video controls preload="metadata" src={apiUrl(item.play_url)} />
                </div>
              ) : (
                <div className="asset-placeholder"><FileText size={28} /><span>{item.assigned_platform?.replaceAll("_", " ")}</span></div>
              )}
              <div className="asset-body">
                <h3>{item.display_hook || item.hook || "Untitled asset"}</h3>
                <p className="asset-caption">{item.display_caption || item.summary || "Campaign copy is ready for review."}</p>
                {item.post_markdown ? <pre className="post-markdown compact">{item.post_markdown}</pre> : null}
                <p className="asset-copy-hint">
                  Hook is the opening line. Caption is the body you paste. Copy post takes the full markdown file.
                </p>
                <div className="asset-copy-row">
                  <CopyButton text={item.display_hook || item.hook} label="Copy hook" />
                  <CopyButton text={item.display_caption || item.summary} label="Copy caption" />
                  <CopyButton text={itemPostText(item)} label="Copy post" />
                </div>
                <div className="asset-foot">
                  <span className="cal-chip">
                    <BrandIcon platform={item.assigned_platform} size={14} label={item.assigned_platform} />
                    {(item.assigned_platform || "").replaceAll("_", " ")}
                  </span>
                  <span>{item.duration_seconds ? `${Math.round(item.duration_seconds)}s` : ""}</span>
                </div>
              </div>
            </article>
          ))}
          </div>
          {deckKeys.length > 0 && (
              <section className="panel posts-deck">
                <div className="section-heading">
                  <div>
                    <span className="overline">Campaign posts</span>
                    <h2>Copy the markdown from this run</h2>
                  </div>
                  <CopyButton text={decks[currentDeck]} label="Copy platform posts" />
                </div>
                <p className="asset-copy-hint">
                  Each clip has a hook (first line), a caption (the rest of the post), and a full markdown file you can paste into LinkedIn, X, or YouTube.
                </p>
                <div className="platform-tabs posts-deck-tabs">
                  {deckKeys.map((platform) => (
                    <button
                      key={platform}
                      className={currentDeck === platform ? "active" : ""}
                      onClick={() => setDeckPlatform(platform)}
                    >
                      {platform.replaceAll("_", " ")}
                    </button>
                  ))}
                </div>
                <pre className="post-markdown">{decks[currentDeck]}</pre>
              </section>
          )}
          <CalendarMonth
            calendar={board.calendar}
            holds={holds}
            onHold={(platform, year, month) => applyHold(platform, false, year, month)}
            onResume={(platform, year, month) => applyHold(platform, true, year, month)}
            onPause={pauseItem}
            onResumeItem={resumeItem}
            onSkip={skipItem}
            onStatus={setItemStatus}
          />
        </>
      )}
    </AppShell>
  );
}

function CalendarStudio() {
  const [payload, setPayload] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const load = () =>
    creatorApi.calendar().then(setPayload).catch((err) => setError(err.message));

  useEffect(() => {
    load();
  }, []);

  const holds = payload?.holds || payload?.calendar?.holds || {};
  const run = async (fn, key) => {
    setBusy(key);
    try {
      const data = await fn();
      setPayload({ calendar: data.calendar, holds: data.holds });
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <AppShell flow={false}>
      <PageHeading
        eyebrow="Posting"
        title="This month, on your terms"
        description="Clips are already made. Pause a whole platform or any single date — nothing is deleted, and you can resume anytime."
        aside={busy ? <LoaderCircle className="spin" size={18} /> : null}
      />
      {error && <Notice>{error}</Notice>}
      {payload?.calendar ? (
        <CalendarMonth
          calendar={payload.calendar}
          holds={holds}
          onHold={(platform, year, month) => run(() => creatorApi.holdPlatform(platform, year, month), platform)}
          onResume={(platform, year, month) => run(() => creatorApi.resumePlatform(platform, year, month), platform)}
          onPause={(itemId, year, month) => run(() => creatorApi.pausePost(itemId, year, month), itemId)}
          onResumeItem={(itemId, year, month) => run(() => creatorApi.resumePost(itemId, year, month), itemId)}
          onSkip={(itemId, year, month) => run(() => creatorApi.skipPost(itemId, year, month), itemId)}
          onStatus={(itemId, status, year, month) => run(() => creatorApi.setPostStatus(itemId, status, year, month), itemId)}
        />
      ) : (
        <div className="loading-state">
          <LoaderCircle className="spin" />
          <span>If this is empty, generate a campaign first.</span>
        </div>
      )}
    </AppShell>
  );
}

function WorkspacePage({ accounts, refreshAccounts, accountBusy, setCampaign }) {
  const auth = useAuth();
  const navigate = useNavigate();
  const connected = (accounts || []).filter((item) => item.connected);
  const [brandForm, setBrandForm] = useState(() => formFromBrand());
  const [logoUploading, setLogoUploading] = useState(false);
  const [brandSaving, setBrandSaving] = useState(false);
  const [brandError, setBrandError] = useState("");
  const [brandSaved, setBrandSaved] = useState(false);

  useEffect(() => {
    creatorApi.getBrand().then((brand) => setBrandForm(formFromBrand(brand))).catch(() => {});
  }, []);

  const syncCampaign = (form) => {
    if (!setCampaign) return;
    setCampaign((current) => ({
      ...current,
      brandName: form.brandName,
      website: form.website,
      tagline: form.tagline,
      endScreenEnabled: form.endScreenEnabled,
      endScreenDuration: form.endScreenDuration,
      endScreenTemplate: form.endScreenTemplate,
      endScreenCta: form.endScreenCta,
      onScreenCaptionsEnabled: form.onScreenCaptionsEnabled,
      hasLogo: form.hasLogo,
      logoCache: form.logoCache,
    }));
  };

  const handleLogo = async (file) => {
    if (!file) return;
    setLogoUploading(true);
    setBrandError("");
    try {
      await creatorApi.uploadLogo(file);
      const next = { ...brandForm, hasLogo: true, logoCache: Date.now(), logoName: file.name };
      setBrandForm(next);
      syncCampaign(next);
    } catch (uploadError) {
      setBrandError(uploadError.message);
    } finally {
      setLogoUploading(false);
    }
  };

  const handleClearLogo = async () => {
    try {
      await creatorApi.clearLogo();
      const next = { ...brandForm, hasLogo: false, logoName: "", logoPreview: "" };
      setBrandForm(next);
      syncCampaign(next);
    } catch (clearError) {
      setBrandError(clearError.message);
    }
  };

  const saveBrand = async () => {
    if (brandForm.endScreenEnabled && !String(brandForm.brandName || "").trim()) {
      setBrandError("Brand name is required for the end screen.");
      return;
    }
    setBrandSaving(true);
    setBrandError("");
    setBrandSaved(false);
    try {
      const saved = await creatorApi.saveBrand(brandPayloadFromForm(brandForm));
      const next = formFromBrand(saved);
      setBrandForm(next);
      syncCampaign(next);
      setBrandSaved(true);
    } catch (saveError) {
      setBrandError(saveError.message);
    } finally {
      setBrandSaving(false);
    }
  };

  return (
    <AppShell flow={false}>
      <PageHeading
        eyebrow="Settings"
        title="Your workspace"
        description="Branding, accounts, schedule control, and sign out — the whole campaign stays here."
      />
      <section className="panel campaign-panel">
        <div className="section-heading">
          <div>
            <span className="overline">Signed in</span>
            <h2>{auth.user?.user_metadata?.full_name || "Creator"}</h2>
          </div>
        </div>
        <p className="account-copy">{auth.user?.email}</p>
        <div className="page-actions">
          <button className="danger-button" onClick={() => auth.signOut()}>
            <LogOut size={16} /> Sign out
          </button>
          <button className="secondary-button" onClick={() => navigate("/calendar")}>
            <CalendarDays size={16} /> Posting calendar
          </button>
        </div>
      </section>
      <section className="panel campaign-panel" style={{ marginTop: 18 }}>
        <div className="section-heading">
          <div>
            <span className="overline">Channels</span>
            <h2>{connected.length} connected</h2>
          </div>
          <button className="secondary-button" onClick={refreshAccounts} disabled={accountBusy}>
            <RefreshCw className={accountBusy ? "spin" : ""} size={16} /> Refresh
          </button>
        </div>
        <div className="calendar-legend" style={{ marginTop: 16 }}>
          {["youtube", "instagram", "linkedin", "twitter"].map((key) => {
            const account = (accounts || []).find((row) => row.platform === key);
            return (
              <span className={`cal-chip ${account?.connected ? "" : "held"}`} key={key}>
                <BrandIcon platform={key} size={16} label={key} />
                {PLATFORM_META[key]?.name} · {account?.connected ? "live" : "not connected"}
              </span>
            );
          })}
        </div>
        <div className="page-actions">
          <button className="primary-button" onClick={() => navigate("/accounts")}>
            <Link2 size={16} /> Manage connections
          </button>
        </div>
      </section>
      <section className="panel campaign-panel" style={{ marginTop: 18 }}>
        <div className="section-heading">
          <div>
            <span className="overline">Branding</span>
            <h2>End screen</h2>
          </div>
          <button className="primary-button compact" onClick={saveBrand} disabled={brandSaving}>
            {brandSaving ? <LoaderCircle className="spin" size={16} /> : null}
            Save branding
          </button>
        </div>
        <BrandingFields
          value={brandForm}
          onChange={setBrandForm}
          logoUploading={logoUploading}
          onLogoUpload={handleLogo}
          onClearLogo={handleClearLogo}
        />
        {brandError ? <Notice>{brandError}</Notice> : null}
        {brandSaved ? <Notice type="success">Brand end screen saved. It applies to the next campaign you generate.</Notice> : null}
      </section>
    </AppShell>
  );
}

function GoogleMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 48 48" aria-hidden="true">
      <path fill="#FFC107" d="M43.6 20.5H42V20H24v8h11.3C33.7 32.7 29.3 36 24 36c-6.6 0-12-5.4-12-12s5.4-12 12-12c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34.2 6.1 29.4 4 24 4 12.9 4 4 12.9 4 24s8.9 20 20 20 20-8.9 20-20c0-1.2-.1-2.3-.4-3.5z" />
      <path fill="#FF3D00" d="M6.3 14.7l6.6 4.8C14.7 16 19 12 24 12c3.1 0 5.8 1.2 8 3.1l5.7-5.7C34.2 6.1 29.4 4 24 4 16.3 4 9.6 8.3 6.3 14.7z" />
      <path fill="#4CAF50" d="M24 44c5.2 0 10-2 13.6-5.2l-6.3-5.3C29.2 35.3 26.7 36 24 36c-5.3 0-9.7-3.3-11.3-8l-6.5 5C9.5 39.6 16.2 44 24 44z" />
      <path fill="#1976D2" d="M43.6 20.5H42V20H24v8h11.3c-1.1 3.2-3.5 5.8-6.7 7.2l.1.1 6.3 5.3C36.9 41.5 44 36 44 24c0-1.2-.1-2.3-.4-3.5z" />
    </svg>
  );
}

function AuthProductPreview() {
  return (
    <div className="auth-preview" aria-hidden="true">
      <div className="auth-preview-card">
        <div className="auth-preview-live"><Sparkles size={12} /> AI analyzing</div>
        <div className="auth-preview-source">
          <Mic size={16} />
          <div>
            <strong>62 min podcast</strong>
            <span>My Podcast · 62:14</span>
          </div>
        </div>
        <div className="auth-waveform">
          {Array.from({ length: 18 }).map((_, index) => <i key={index} style={{ "--i": index }} />)}
        </div>
        <em>✨ 18 moments found</em>
      </div>
      <div className="auth-preview-arrow">↓</div>
      <div className="auth-preview-outputs">
        <div><span>REEL</span><b>00:42</b></div>
        <div><span>SHORT</span><b>00:37</b></div>
        <div><span>LINKEDIN</span><b>POST</b></div>
      </div>
      <div className="auth-month">
        <span>Your next 30 days</span>
        <div className="auth-month-days">
          {["Mon", "Tue", "Wed", "Thu", "Fri"].map((day) => (
            <em key={day}>{day}<i /></em>
          ))}
        </div>
        <p>12 Shorts · 8 Reels · 15 LinkedIn · 20 X · full calendar</p>
      </div>
    </div>
  );
}

function NextStepGuide({ name, onStay, onSkip }) {
  return (
    <div className="guide-overlay" role="dialog" aria-labelledby="guide-title">
      <div className="guide-card">
        <button className="icon-button guide-close" onClick={onStay} aria-label="Close">
          <X size={16} />
        </button>
        <div className="guide-spark"><BrandMark size={42} /></div>
        <h3 id="guide-title">Hey {name} — here's what to do next</h3>
        <p>You're on Accounts. Three steps, then you have a month of content.</p>
        <ol className="guide-steps">
          <li className="current">
            <span>1</span>
            <div>
              <strong>Connect a channel</strong>
              <small>You're here. Optional — skip if you just want to generate.</small>
            </div>
          </li>
          <li>
            <span>2</span>
            <div>
              <strong>Upload one long video</strong>
              <small>Podcast, interview, or any talk.</small>
            </div>
          </li>
          <li>
            <span>3</span>
            <div>
              <strong>Get a 30-day calendar</strong>
              <small>Shorts, Reels, LinkedIn, and X — planned for you.</small>
            </div>
          </li>
        </ol>
        <button className="primary-button full" onClick={onStay}>I'll connect a channel</button>
        <button className="text-button full" onClick={onSkip}>Skip — upload a video instead</button>
      </div>
    </div>
  );
}

function AuthScreen() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState("signin");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [googleReady, setGoogleReady] = useState(Boolean(auth.cloud));

  useEffect(() => {
    if (auth.cloud) {
      setGoogleReady(true);
      return;
    }
    creatorApi.authConfig()
      .then((data) => setGoogleReady(Boolean(data.google_signin || data.google_client_id)))
      .catch(() => setGoogleReady(false));
  }, [auth.cloud]);

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (mode === "reset") {
        const { error } = await auth.resetPassword(form.email);
        if (error) throw error;
        setMessage("Password reset link sent. Check your inbox.");
      } else if (mode === "signup") {
        const { error } = await auth.signUp(form.email, form.password, form.name);
        if (error) throw error;
        setMessage(auth.cloud ? "Account created. Check your email if confirmation is required." : "Workspace ready. You’re in.");
        sessionStorage.setItem("creatoros.fresh-session", "1");
        navigate("/accounts", { replace: true });
      } else {
        const { error } = await auth.signIn(form.email, form.password);
        if (error) throw error;
        sessionStorage.setItem("creatoros.fresh-session", "1");
        navigate("/accounts", { replace: true });
      }
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  const googleSignIn = async () => {
    setBusy(true);
    setMessage("");
    try {
      const { error } = await auth.signInWithGoogle();
      if (error) throw error;
      sessionStorage.setItem("creatoros.fresh-session", "1");
      if (!auth.cloud) navigate("/accounts", { replace: true });
    } catch (error) {
      setMessage(error.message);
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-visual">
        <div className="auth-orbs" aria-hidden="true">
          <span />
          <span />
          <span />
        </div>
        <Logo />
        <div className="auth-copy">
          <div className="eyebrow">CREATE · REPURPOSE · SCHEDULE</div>
          <h1>One video.<br />A month of content.</h1>
          <p>
            Upload one podcast, interview, or long-form video. creatorOS turns it
            into platform-ready Shorts, Reels, LinkedIn posts, and a complete 30-day calendar.
          </p>
          <div className="auth-benefits">
            <span><CheckCircle2 /> Turn one video into weeks of content</span>
            <span><CheckCircle2 /> Generate once, post across every platform</span>
            <span><CheckCircle2 /> Control your entire content calendar</span>
          </div>
        </div>
        <AuthProductPreview />
      </div>
      <div className="auth-panel">
        <form onSubmit={submit}>
          <div className="auth-icon"><BrandMark size={48} /></div>
          <h2>{mode === "signup" ? "Create your workspace" : mode === "reset" ? "Reset your password" : "Welcome back."}</h2>
          <p>
            {mode === "signup"
              ? "A few details, then we’ll show you exactly what to do next."
              : mode === "reset"
                ? "We’ll email you a reset link."
                : "Continue to your studio."}
          </p>
          {mode === "signin" && googleReady && (
            <>
              <button type="button" className="google-button" disabled={busy} onClick={googleSignIn}>
                <GoogleMark /> Continue with Google
              </button>
              <div className="auth-or">or</div>
            </>
          )}
          {mode === "signup" && <Field label="Your name"><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Ananya Singh" autoComplete="name" /></Field>}
          <Field label="Email address"><input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="you@example.com" autoComplete="email" /></Field>
          {mode !== "reset" && <Field label="Password"><input required minLength={8} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="••••••••" autoComplete={mode === "signup" ? "new-password" : "current-password"} /></Field>}
          {message && <div className="auth-message">{message}</div>}
          <button className="primary-button full" disabled={busy}>{busy && <LoaderCircle className="spin" size={17} />}{mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : "Sign in"}</button>
          <div className="auth-links">
            {mode === "signin" && <button type="button" onClick={() => setMode("reset")}>Forgot password?</button>}
            <button type="button" onClick={() => setMode(mode === "signup" ? "signin" : "signup")}>{mode === "signup" ? "Already have an account? Sign in" : "New to creatorOS? Create account"}</button>
            {mode === "reset" && <button type="button" onClick={() => setMode("signin")}>Back to sign in</button>}
          </div>
        </form>
      </div>
    </div>
  );
}

function CreatorApp() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [campaign, setCampaign] = useStoredState("creatoros-campaign", DEFAULT_CAMPAIGN);
  const [plan, setPlan] = useStoredState("creatoros-plan", DEFAULT_PLAN);
  const [currentJob, setCurrentJob] = useStoredState("creatoros-current-job", "");
  const [accounts, setAccounts] = useState([]);
  const [accountBusy, setAccountBusy] = useState(false);
  const [generating, setGenerating] = useState(false);

  const refreshAccounts = useCallback(async () => {
    setAccountBusy(true);
    try {
      const data = await creatorApi.accounts();
      setAccounts(data.accounts || []);
    } catch {
      setAccounts([]);
    } finally {
      setAccountBusy(false);
    }
  }, []);

  useEffect(() => {
    refreshAccounts();
    window.addEventListener("focus", refreshAccounts);
    return () => window.removeEventListener("focus", refreshAccounts);
  }, [refreshAccounts]);

  const generate = async () => {
    if (campaign.endScreenEnabled && !String(campaign.brandName || "").trim()) {
      window.alert("Brand name is required for the end screen.");
      return;
    }
    setGenerating(true);
    try {
      const contentPlan = Object.fromEntries(
        Object.entries(plan).filter(([, item]) => item.enabled).map(([key, item]) => [
          key,
          { count: item.count, interval_days: item.interval_days, purpose: item.purpose },
        ]),
      );
      let savedBrand = {};
      try {
        savedBrand = await creatorApi.getBrand();
      } catch {
        savedBrand = {};
      }
      const { has_logo: _hasLogo, logo_url: _logoUrl, ...brandRest } = savedBrand;
      const endScreenOn = Boolean(campaign.endScreenEnabled);
      const brandPayload = {
        ...brandRest,
        brand_name: campaign.brandName,
        website: campaign.website,
        tagline: campaign.tagline || savedBrand.tagline || "",
        goal: campaign.goal,
        audience: campaign.audience,
        tone: campaign.tone,
        show_type: campaign.showType || "auto",
        campaign_duration_days: campaign.durationDays,
        campaign_start_date: campaign.startDate,
        logo_path: savedBrand.logo_path || "",
        end_screen_enabled: endScreenOn,
        end_screen_duration: Number(campaign.endScreenDuration || savedBrand.end_screen_duration || 3),
        end_screen_template: campaign.endScreenTemplate || savedBrand.end_screen_template || "logo_name_website",
        end_screen_cta: campaign.endScreenCta || savedBrand.end_screen_cta || "",
        on_screen_captions_enabled: campaign.onScreenCaptionsEnabled !== false,
      };
      // Save before queueing so the worker always reads the toggle the user sees.
      try {
        await creatorApi.saveBrand(brandPayload);
      } catch {
        /* brand_context on the job is the source of truth below */
      }
      const result = await creatorApi.startCampaign({
        source: campaign.source,
        campaign_start_date: campaign.startDate,
        content_plan: contentPlan,
        brand_context: brandPayload,
      });
      setCurrentJob(result.job_id);
      navigate(`/processing/${result.job_id}`);
    } catch (error) {
      window.alert(error.message);
    } finally {
      setGenerating(false);
    }
  };

  if (auth.loading) return <div className="app-loading"><BrandMark /><LoaderCircle className="spin" /></div>;
  if (!auth.user) return <AuthScreen />;

  const oauthResult = ["youtube", "instagram", "linkedin", "twitter"].some((key) =>
    new URLSearchParams(location.search).get(key),
  );
  if (oauthResult && location.pathname !== "/accounts") {
    return <Navigate to={`/accounts${location.search}`} replace />;
  }

  return (
    <Routes>
      <Route path="/" element={<HomePage currentJob={currentJob} />} />
      <Route path="/accounts" element={<ConnectPage accounts={accounts} refreshAccounts={refreshAccounts} accountBusy={accountBusy} />} />
      <Route path="/campaign" element={<CampaignPage campaign={campaign} setCampaign={setCampaign} />} />
      <Route path="/strategy" element={<StrategyPage campaign={campaign} plan={plan} setPlan={setPlan} onGenerate={generate} generating={generating} />} />
      <Route path="/processing/:jobId?" element={<ProcessingPage currentJob={currentJob} onComplete={setCurrentJob} plan={plan} setPlan={setPlan} />} />
      <Route path="/complete/:jobId" element={<CompletionPage currentJob={currentJob} />} />
      <Route path="/results/:jobId" element={<ResultsPage currentJob={currentJob} />} />
      <Route path="/calendar" element={<CalendarStudio />} />
      <Route path="/workspace" element={<WorkspacePage accounts={accounts} refreshAccounts={refreshAccounts} accountBusy={accountBusy} setCampaign={setCampaign} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return <AuthProvider><CreatorApp /></AuthProvider>;
}
