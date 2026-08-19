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
  BarChart3,
  BriefcaseBusiness as Linkedin,
  Camera as Instagram,
  Check,
  CheckCircle2,
  ChevronRight,
  Circle,
  Clock3,
  Download,
  ExternalLink,
  FileVideo,
  Film,
  Link2,
  LoaderCircle,
  LogOut,
  Menu,
  Play,
  PlaySquare as Youtube,
  Plus,
  RefreshCw,
  Rocket,
  Settings2,
  Sparkles,
  Trash2,
  Upload,
  WandSparkles,
  X,
  Zap,
} from "lucide-react";
import { AuthProvider, useAuth } from "./auth";
import { apiUrl, creatorApi } from "./api";
import {
  DEFAULT_CAMPAIGN,
  DEFAULT_PLAN,
  FLOW_STEPS,
  PLATFORM_META,
  PROCESSING_STEPS,
} from "./campaign";
import LOGO_URL from "./assets/creatoros-logo.png";

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

function Logo() {
  return (
    <div className="brand">
      <div className="brand-mark">
        <img src={LOGO_URL} alt="" />
      </div>
      <div>
        <strong>CreatorOS</strong>
        <span>One episode. A complete campaign.</span>
      </div>
    </div>
  );
}

function AppShell({ children, step, user }) {
  const navigate = useNavigate();
  const [menuOpen, setMenuOpen] = useState(false);
  const auth = useAuth();
  const activeIndex = FLOW_STEPS.findIndex((item) => item.id === step);

  return (
    <div className="app-shell">
      <aside className={menuOpen ? "sidebar open" : "sidebar"}>
        <div className="sidebar-top">
          <Logo />
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(false)}>
            <X size={20} />
          </button>
        </div>
        <nav className="side-nav">
          <button className="active" onClick={() => navigate("/")}>
            <Rocket size={18} /> New campaign
          </button>
          <button onClick={() => navigate("/results/latest")}>
            <BarChart3 size={18} /> Campaign library
          </button>
          <button>
            <Settings2 size={18} /> Workspace
          </button>
        </nav>
        <div className="sidebar-card">
          <div className="mini-icon"><Zap size={16} /></div>
          <div>
            <strong>Editor-first AI</strong>
            <p>Audio, picture, words, and platform intent—scored together.</p>
          </div>
        </div>
        <div className="account-chip">
          <div className="avatar">
            {(user?.email || "Local").slice(0, 1).toUpperCase()}
          </div>
          <div>
            <strong>{user?.user_metadata?.full_name || "Local workspace"}</strong>
            <span>{user?.email || "Development mode"}</span>
          </div>
          {auth.enabled && (
            <button className="icon-button" onClick={() => auth.signOut()} title="Sign out">
              <LogOut size={17} />
            </button>
          )}
        </div>
      </aside>

      <main className="main-shell">
        <header className="topbar">
          <button className="icon-button mobile-only" onClick={() => setMenuOpen(true)}>
            <Menu size={21} />
          </button>
          <div className="mobile-brand"><Logo /></div>
          <div className="topbar-actions">
            <span className="status-pill"><span /> Systems ready</span>
            <button className="ghost-button"><Settings2 size={16} /> Settings</button>
          </div>
        </header>

        <div className="workspace">
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

const platformIcons = {
  youtube: Youtube,
  instagram: Instagram,
  linkedin: Linkedin,
  twitter: X,
};

function ConnectPage({ accounts, refreshAccounts, accountBusy }) {
  const navigate = useNavigate();
  const location = useLocation();
  const [message, setMessage] = useState("");
  const [disconnecting, setDisconnecting] = useState(false);
  const accountMap = useMemo(
    () => Object.fromEntries((accounts || []).map((account) => [account.platform, account])),
    [accounts],
  );
  const connectedCount = accounts.filter((item) => item.connected).length;

  useEffect(() => {
    const result = new URLSearchParams(location.search).get("youtube");
    if (result === "connected") {
      setMessage("YouTube connected successfully. Your channel is ready for approved uploads.");
      refreshAccounts();
      window.history.replaceState({}, "", window.location.pathname);
    } else if (result === "denied") {
      setMessage("YouTube permission was not granted. You can try again whenever you are ready.");
      window.history.replaceState({}, "", window.location.pathname);
    }
  }, [location.search, refreshAccounts]);

  const connectYouTube = () => {
    window.open(apiUrl("/connect/youtube"), "_blank", "noopener,noreferrer");
    setMessage("Finish Google authorization in the new tab, then return here.");
  };

  const disconnectYouTube = async () => {
    setDisconnecting(true);
    try {
      await creatorApi.disconnectYouTube();
      setMessage("YouTube disconnected from this workspace.");
      await refreshAccounts();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setDisconnecting(false);
    }
  };

  return (
    <AppShell step="connect">
      <PageHeading
        eyebrow="Step 1 of 4"
        title="Connect your publishing channels"
        description="Connect only what you need. You can change or disconnect an account at any time."
        aside={<div className="linked-count"><strong>{connectedCount}</strong> of 4 linked</div>}
      />

      {message && <Notice type={message.includes("success") ? "success" : "info"} onClose={() => setMessage("")}>{message}</Notice>}

      <div className="account-grid">
        {Object.entries(PLATFORM_META).map(([key, meta]) => {
          const account = accountMap[key] || { connected: false, status: "not_connected" };
          const Icon = platformIcons[key];
          const available = key === "youtube";
          return (
            <article className={`account-card ${account.connected ? "connected" : ""}`} key={key}>
              <div className="account-card-head">
                <div className={`platform-icon ${meta.tone}`}><Icon size={21} /></div>
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
                      <div><strong>Ready to publish</strong><span>Uploads default to private during testing</span></div>
                    </div>
                    <div className="card-actions">
                      <button className="secondary-button" onClick={connectYouTube}>
                        <RefreshCw size={16} /> Change account
                      </button>
                      <button className="danger-button" onClick={disconnectYouTube} disabled={disconnecting}>
                        {disconnecting ? <LoaderCircle className="spin" size={16} /> : <Trash2 size={16} />}
                        Disconnect
                      </button>
                    </div>
                  </>
                ) : available ? (
                  <>
                    <p className="account-copy">Authorize CreatorOS to upload only the Shorts you approve.</p>
                    <button className="primary-button compact" onClick={connectYouTube}>
                      <Link2 size={16} /> Connect YouTube
                    </button>
                  </>
                ) : (
                  <>
                    <p className="account-copy">OAuth support for this platform is on the roadmap.</p>
                    <button className="secondary-button" disabled>Coming soon</button>
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
          Continue to campaign <ArrowRight size={17} />
        </button>
        <button className="text-button" onClick={() => navigate("/campaign")}>Skip for now</button>
        <button className="secondary-button push-right" onClick={refreshAccounts} disabled={accountBusy}>
          <RefreshCw className={accountBusy ? "spin" : ""} size={16} /> Refresh status
        </button>
      </div>
    </AppShell>
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
  const [error, setError] = useState("");
  const update = (key, value) => setCampaign((current) => ({ ...current, [key]: value }));

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

  const continueNext = () => {
    if (!campaign.source.trim()) {
      setError(campaign.sourceType === "url" ? "Paste a YouTube or podcast URL to continue." : "Choose a video file to continue.");
      return;
    }
    setError("");
    navigate("/strategy");
  };

  return (
    <AppShell step="campaign">
      <PageHeading
        eyebrow="Step 2 of 4"
        title="Tell us what this campaign should achieve"
        description="One source, one clear audience, and a goal. CreatorOS handles the downstream decisions."
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
          <Field label="Podcast or YouTube URL" hint="Any public episode or video link." wide>
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
    instagram_reels: ["Instagram Reels", Instagram],
    youtube_shorts: ["YouTube Shorts", Youtube],
    linkedin: ["LinkedIn", Linkedin],
    twitter: ["Twitter / X", X],
  };
  const totals = Object.values(plan).filter((item) => item.enabled).reduce((sum, item) => sum + item.count, 0);
  const update = (key, patch) => setPlan((current) => ({ ...current, [key]: { ...current[key], ...patch } }));

  return (
    <AppShell step="strategy">
      <PageHeading
        eyebrow="Step 3 of 4"
        title="Shape the campaign before AI starts"
        description="Tune volume and cadence by platform. Nothing gets posted without your approval."
      />
      <div className="strategy-layout">
        <div className="strategy-grid">
          {Object.entries(plan).map(([key, item]) => {
            const [name, Icon] = platformNames[key];
            return (
              <article className={`strategy-card ${item.enabled ? "" : "disabled"}`} key={key}>
                <div className="strategy-head">
                  <div className="platform-icon purple"><Icon size={20} /></div>
                  <div><h3>{name}</h3><p>{item.suggested}</p></div>
                  <button className={`toggle ${item.enabled ? "on" : ""}`} onClick={() => update(key, { enabled: !item.enabled })}><span /></button>
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
              <div key={key}><span>{platformNames[key][0]}</span><strong>{item.count}</strong></div>
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

function formatRemaining(progress, elapsed) {
  if (!progress || progress < 4 || !elapsed) return "Estimating…";
  const remaining = Math.max(0, (elapsed / progress) * (100 - progress));
  if (remaining < 60) return "Less than a minute";
  return `About ${Math.ceil(remaining / 60)} min`;
}

function ProcessingPage({ currentJob, onComplete }) {
  const { jobId: paramJobId } = useParams();
  const navigate = useNavigate();
  const jobId = paramJobId || currentJob;
  const [status, setStatus] = useState(null);
  const [pollError, setPollError] = useState("");

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
        if (next.status === "completed") {
          onComplete?.(jobId);
          timer = setTimeout(() => navigate(`/complete/${jobId}`), 900);
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
  }, [jobId, navigate, onComplete]);

  if (!jobId) return <Navigate to="/strategy" replace />;

  const progress = status?.progress_percent || 0;
  const backendSteps = status?.steps || [];
  const activeStep = PROCESSING_STEPS[Math.max((status?.step_index || 1) - 1, 0)];

  return (
    <AppShell step="processing">
      <PageHeading
        eyebrow={`Campaign ${jobId.slice(0, 8)}`}
        title={status?.status === "completed" ? "Your campaign is ready" : "Building your campaign"}
        description={status?.status === "completed" ? "Every asset has been edited, written, scheduled, and packaged." : "You can leave this page open—we’ll keep every stage visible while CreatorOS works."}
        aside={<div className="live-badge"><span /> Live processing</div>}
      />
      <section className="processing-hero">
        <div className="progress-summary">
          <div className="progress-ring" style={{ "--progress": `${progress * 3.6}deg` }}>
            <div><strong>{progress}%</strong><span>complete</span></div>
          </div>
          <div className="progress-copy">
            <span className="overline">Working now</span>
            <h2>{status?.step_label || "Preparing the campaign"}</h2>
            <p>{activeStep?.description || "CreatorOS is getting the workspace ready."}</p>
            <div className="progress-track"><span style={{ width: `${progress}%` }} /></div>
            <div className="progress-meta">
              <span><Clock3 size={15} /> Elapsed: {status?.elapsed_human || "0s"}</span>
              <span><Zap size={15} /> Remaining: {formatRemaining(progress, status?.elapsed_seconds)}</span>
            </div>
          </div>
        </div>
        {status?.status === "failed" && <Notice>{status.error || "The campaign stopped unexpectedly."}</Notice>}
        {pollError && <Notice>Connection interrupted: {pollError}. Retrying automatically…</Notice>}
      </section>

      <div className="processing-layout">
        <section className="panel timeline-panel">
          <div className="section-heading"><div><span className="overline">Live workflow</span><h2>What CreatorOS is doing</h2></div><span>{backendSteps.filter((s) => s.status === "done").length} / 9 complete</span></div>
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
                  <div className="timeline-state">{state === "done" ? "Done" : state === "active" ? "In progress" : state === "error" ? "Needs attention" : "Waiting"}</div>
                </div>
              );
            })}
          </div>
        </section>
        <aside className="processing-side">
          <div className="panel compact-panel">
            <div className="summary-title"><Film size={18} /><span>Quality checks</span></div>
            <ul className="check-list">
              <li><CheckCircle2 size={16} /> Audio and picture analyzed together</li>
              <li><CheckCircle2 size={16} /> Different openings for Shorts and Reels</li>
              <li><CheckCircle2 size={16} /> Captions kept inside safe zones</li>
              <li><CheckCircle2 size={16} /> Platform copy rewritten, not duplicated</li>
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

  useEffect(() => {
    creatorApi.board().then(setBoard).catch((err) => setError(err.message));
  }, []);

  const items = board?.items || [];
  const summary = board?.summary || {};
  const platformCounts = items.reduce((counts, item) => {
    const platform = item.assigned_platform || "other";
    counts[platform] = (counts[platform] || 0) + 1;
    return counts;
  }, {});
  const scan = board?.scan || summary.scan || {};
  const scannedMinutes = scan.scanned_seconds
    ? Math.max(1, Math.round(scan.scanned_seconds / 60))
    : null;
  const sourceMinutes = scan.source_seconds
    ? Math.max(1, Math.round(scan.source_seconds / 60))
    : null;

  return (
    <AppShell step="processing">
      <section className="completion-hero">
        <div className="completion-burst"><Check size={34} /></div>
        <div>
          <div className="eyebrow">Campaign complete</div>
          <h1>Your content engine is ready</h1>
          <p>
            CreatorOS found the strongest moments, directed the edits, wrote each
            platform version, and packaged the full campaign.
          </p>
        </div>
        <div className="completion-actions">
          <button className="primary-button" onClick={() => navigate(`/results/${resolvedJob}`)}>
            Open campaign library <ArrowRight size={17} />
          </button>
          {resolvedJob && (
            <a className="secondary-button" href={apiUrl(`/download-campaign/${resolvedJob}`)}>
              <Download size={16} /> Download package
            </a>
          )}
        </div>
      </section>

      {error && <Notice>{error}</Notice>}

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
          <div className="kpi-icon"><Zap size={20} /></div>
          <span>Estimated AI cost</span>
          <strong>
            {summary.estimated_cost_usd != null
              ? `$${summary.estimated_cost_usd}`
              : "—"}
          </strong>
          <small>Gemini usage</small>
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
            <div className="summary-title"><Zap size={18} /><span>Editor efficiency</span></div>
            {scannedMinutes ? (
              <>
                <strong>
                  {scannedMinutes} min watched
                  {sourceMinutes ? ` of ${sourceMinutes} min` : ""}
                </strong>
                <p>
                  {scan.stopped_early
                    ? "The editor found enough strong moments and skipped the weak remainder."
                    : "The source was watched and listened to for standout moments."}
                </p>
              </>
            ) : (
              <p>Audio-visual analysis was used to rank the final moments.</p>
            )}
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

  useEffect(() => {
    creatorApi.board().then(setBoard).catch((err) => setError(err.message));
  }, []);

  const items = board?.items || [];
  const platforms = [...new Set(items.map((item) => item.assigned_platform).filter(Boolean))];
  const visible = activePlatform === "all" ? items : items.filter((item) => item.assigned_platform === activePlatform);
  const summary = board?.summary || {};

  return (
    <AppShell step="processing">
      <PageHeading
        eyebrow="Campaign complete"
        title="Review your campaign"
        description="Preview the edits, approve the copy, and download the complete package."
        aside={resolvedJob && <a className="primary-button" href={apiUrl(`/download-campaign/${resolvedJob}`)}><Download size={17} /> Download campaign</a>}
      />
      {error && <Notice>{error}</Notice>}
      <div className="result-kpis">
        <div><Film size={19} /><span>Content pieces</span><strong>{summary.total_content_pieces || items.length || "—"}</strong></div>
        <div><Play size={19} /><span>Video edits</span><strong>{board?.video_renders ?? "—"}</strong></div>
        <div><Clock3 size={19} /><span>Processing time</span><strong>{summary.processing_human || "—"}</strong></div>
        <div><Sparkles size={19} /><span>Analysis</span><strong>{board?.analysis_mode === "audio_visual" ? "Audio + visual" : "Audio-first"}</strong></div>
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
        <div className="asset-grid">
          {visible.map((item, index) => (
            <article className="asset-card" key={item.id || `${item.assigned_platform}-${index}`}>
              {item.play_url ? (
                <video controls preload="metadata" src={apiUrl(item.play_url)} />
              ) : (
                <div className="asset-placeholder"><Film size={28} /><span>{item.assigned_platform?.replaceAll("_", " ")}</span></div>
              )}
              <div className="asset-body">
                <div className="asset-meta"><span>{item.package_label || "Platform cut"}</span><strong>Score {item.overall_score || "—"}</strong></div>
                <h3>{item.display_hook || item.hook || "Untitled asset"}</h3>
                <p>{item.display_caption || item.summary || "Campaign copy is ready for review."}</p>
                <div className="asset-foot"><span>{item.scheduled_date || "Unscheduled"}</span><span>{item.duration_seconds ? `${item.duration_seconds}s` : item.assigned_platform?.replaceAll("_", " ")}</span></div>
              </div>
            </article>
          ))}
        </div>
      )}
    </AppShell>
  );
}

function AuthScreen() {
  const auth = useAuth();
  const [mode, setMode] = useState("signin");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

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
        setMessage("Account created. Check your email to confirm your address.");
      } else {
        const { error } = await auth.signIn(form.email, form.password);
        if (error) throw error;
      }
    } catch (error) {
      setMessage(error.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-visual">
        <Logo />
        <div className="auth-copy">
          <div className="eyebrow">Your content operating system</div>
          <h1>Turn one conversation into weeks of content.</h1>
          <p>Find the strongest moments, edit platform-native cuts, write the campaign, and keep publishing on schedule.</p>
          <div className="auth-benefits">
            <span><CheckCircle2 /> Editor-grade short-form direction</span>
            <span><CheckCircle2 /> Platform-specific writing and scheduling</span>
            <span><CheckCircle2 /> Your campaigns stay private to your account</span>
          </div>
        </div>
      </div>
      <div className="auth-panel">
        <form onSubmit={submit}>
          <div className="auth-icon"><Sparkles size={22} /></div>
          <h2>{mode === "signup" ? "Create your workspace" : mode === "reset" ? "Reset your password" : "Welcome back"}</h2>
          <p>{mode === "signup" ? "Start building your first campaign." : mode === "reset" ? "We’ll email you a secure reset link." : "Sign in to continue to CreatorOS."}</p>
          {mode === "signup" && <Field label="Your name"><input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>}
          <Field label="Email address"><input required type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} /></Field>
          {mode !== "reset" && <Field label="Password"><input required minLength={8} type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} /></Field>}
          {message && <div className="auth-message">{message}</div>}
          <button className="primary-button full" disabled={busy}>{busy && <LoaderCircle className="spin" size={17} />}{mode === "signup" ? "Create account" : mode === "reset" ? "Send reset link" : "Sign in"}</button>
          <div className="auth-links">
            {mode === "signin" && <button type="button" onClick={() => setMode("reset")}>Forgot password?</button>}
            <button type="button" onClick={() => setMode(mode === "signup" ? "signin" : "signup")}>{mode === "signup" ? "Already have an account? Sign in" : "New to CreatorOS? Create account"}</button>
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
    setGenerating(true);
    try {
      const contentPlan = Object.fromEntries(
        Object.entries(plan).filter(([, item]) => item.enabled).map(([key, item]) => [
          key,
          { count: item.count, interval_days: item.interval_days, purpose: item.purpose },
        ]),
      );
      const result = await creatorApi.startCampaign({
        source: campaign.source,
        campaign_start_date: campaign.startDate,
        content_plan: contentPlan,
        brand_context: {
          brand_name: campaign.brandName,
          website: campaign.website,
          goal: campaign.goal,
          audience: campaign.audience,
          tone: campaign.tone,
          campaign_duration_days: campaign.durationDays,
          campaign_start_date: campaign.startDate,
        },
      });
      setCurrentJob(result.job_id);
      navigate(`/processing/${result.job_id}`);
    } catch (error) {
      window.alert(error.message);
    } finally {
      setGenerating(false);
    }
  };

  if (auth.loading) return <div className="app-loading"><div className="brand-mark"><img src={LOGO_URL} alt="CreatorOS" /></div><LoaderCircle className="spin" /></div>;
  if (auth.enabled && !auth.user) return <AuthScreen />;

  return (
    <Routes>
      <Route path="/" element={<ConnectPage accounts={accounts} refreshAccounts={refreshAccounts} accountBusy={accountBusy} />} />
      <Route path="/campaign" element={<CampaignPage campaign={campaign} setCampaign={setCampaign} />} />
      <Route path="/strategy" element={<StrategyPage campaign={campaign} plan={plan} setPlan={setPlan} onGenerate={generate} generating={generating} />} />
      <Route path="/processing/:jobId?" element={<ProcessingPage currentJob={currentJob} onComplete={setCurrentJob} />} />
      <Route path="/complete/:jobId" element={<CompletionPage currentJob={currentJob} />} />
      <Route path="/results/:jobId" element={<ResultsPage currentJob={currentJob} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return <AuthProvider><CreatorApp /></AuthProvider>;
}
