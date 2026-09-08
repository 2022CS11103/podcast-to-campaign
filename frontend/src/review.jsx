import { useEffect, useMemo, useState } from "react";
import {
  Check,
  Film,
  LoaderCircle,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  X,
} from "lucide-react";
import { BrandIcon } from "./BrandIcon";
import { apiUrl, creatorApi } from "./api";

function needsReviewStatus(status) {
  const raw = String(status || "ai_generated").toLowerCase().replace(/[\s'-]+/g, "_");
  return ["ai_generated", "pending", "draft", "generated", "needs_approval", ""].includes(raw);
}

function platformLabel(platform) {
  const key = String(platform || "");
  return ({
    instagram_reels: "Instagram Reels",
    youtube_shorts: "YouTube Shorts",
    linkedin: "LinkedIn",
    twitter: "X",
    tiktok: "TikTok",
  })[key] || key.replaceAll("_", " ");
}

export function QualityChips({ item }) {
  const reasons = item?.review_reasons || [];
  const score = item?.overall_score ?? item?.quality?.overall_score;
  const topic = item?.detected_topic || item?.content_angle || item?.display_angle;
  return (
    <div className="quality-chips">
      {score != null && score !== "" ? (
        <span className="quality-chip score">Score {Math.round(Number(score))}</span>
      ) : null}
      {topic ? <span className="quality-chip">{topic}</span> : null}
      {reasons.slice(0, 3).map((reason) => (
        <span className="quality-chip reason" key={reason}>{reason}</span>
      ))}
    </div>
  );
}

export function ReviewPage({ AppShell, PageHeading, Notice }) {
  const [board, setBoard] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [filter, setFilter] = useState("needs_review");
  const [platformFilter, setPlatformFilter] = useState("all");

  const loadBoard = () =>
    creatorApi.board().then(setBoard).catch((err) => setError(err.message));

  useEffect(() => {
    loadBoard();
  }, []);

  const items = board?.items || [];
  const platforms = useMemo(
    () => [...new Set(items.map((item) => item.assigned_platform).filter(Boolean))],
    [items]
  );

  const queue = useMemo(() => {
    let list = items;
    if (filter === "approved") {
      list = list.filter((item) => String(item.status || "").toLowerCase() === "scheduled");
    } else if (filter === "rejected") {
      list = list.filter((item) => ["skipped", "rejected"].includes(String(item.status || "").toLowerCase()));
    } else if (filter === "needs_review") {
      list = list.filter((item) => needsReviewStatus(item.status));
    }
    if (platformFilter !== "all") {
      list = list.filter((item) => item.assigned_platform === platformFilter);
    }
    // Keep video clips visible first so Shorts/Reels aren't buried under text posts.
    return [...list].sort((a, b) => {
      const av = a.play_url ? 0 : 1;
      const bv = b.play_url ? 0 : 1;
      if (av !== bv) return av - bv;
      return String(a.assigned_platform || "").localeCompare(String(b.assigned_platform || ""));
    });
  }, [items, filter, platformFilter]);

  const pendingCount = items.filter((item) => needsReviewStatus(item.status)).length;
  const pendingVideos = items.filter(
    (item) => needsReviewStatus(item.status) && Boolean(item.play_url)
  ).length;

  const setStatus = async (itemId, status) => {
    if (!itemId) {
      setError("This clip is missing an id, so it can’t be approved yet.");
      return;
    }
    setBusy(itemId);
    setError("");
    try {
      await creatorApi.setPostStatus(itemId, status);
      await loadBoard();
    } catch (err) {
      setError(err.message || "Could not update status.");
    } finally {
      setBusy("");
    }
  };

  const bulk = async (action) => {
    setBusy(action);
    setError("");
    try {
      const ids = queue.filter((item) => needsReviewStatus(item.status) && item.id).map((item) => item.id);
      await creatorApi.reviewBulk({ action, item_ids: ids.length ? ids : undefined });
      await loadBoard();
    } catch (err) {
      setError(err.message || "Bulk review failed.");
    } finally {
      setBusy("");
    }
  };

  return (
    <AppShell flow={false}>
      <PageHeading
        title="Approve before publish"
        description={`${pendingCount} waiting · ${pendingVideos} video clips`}
        aside={
          <div className="heading-actions">
            <button className="secondary-button" onClick={() => bulk("reject")} disabled={Boolean(busy) || pendingCount === 0}>
              {busy === "reject" ? <LoaderCircle className="spin" size={16} /> : <ThumbsDown size={16} />}
              Reject queue
            </button>
            <button className="primary-button" onClick={() => bulk("approve")} disabled={Boolean(busy) || pendingCount === 0}>
              {busy === "approve" ? <LoaderCircle className="spin" size={16} /> : <ThumbsUp size={16} />}
              Approve pending
            </button>
          </div>
        }
      />
      {error ? <Notice>{error}</Notice> : null}

      <div className="result-kpis">
        <div><Sparkles size={19} /><span>Needs approval</span><strong>{pendingCount}</strong></div>
        <div><Film size={19} /><span>Video clips</span><strong>{pendingVideos}</strong></div>
        <div><Check size={19} /><span>Approved</span><strong>{items.filter((i) => String(i.status).toLowerCase() === "scheduled").length}</strong></div>
        <div><X size={19} /><span>Won't post</span><strong>{items.filter((i) => ["skipped", "rejected"].includes(String(i.status || "").toLowerCase())).length}</strong></div>
      </div>

      <div className="result-toolbar">
        <div className="platform-tabs">
          {[
            ["needs_review", "Needs approval", pendingCount],
            ["approved", "Approved", items.filter((i) => String(i.status).toLowerCase() === "scheduled").length],
            ["rejected", "Rejected", items.filter((i) => ["skipped", "rejected"].includes(String(i.status || "").toLowerCase())).length],
            ["all", "All", items.length],
          ].map(([id, label, count]) => (
            <button key={id} className={filter === id ? "active" : ""} onClick={() => setFilter(id)}>
              {label} <span>{count}</span>
            </button>
          ))}
        </div>
      </div>

      {platforms.length > 0 ? (
        <div className="result-toolbar">
          <div className="platform-tabs">
            <button className={platformFilter === "all" ? "active" : ""} onClick={() => setPlatformFilter("all")}>
              All platforms
            </button>
            {platforms.map((platform) => (
              <button
                key={platform}
                className={platformFilter === platform ? "active" : ""}
                onClick={() => setPlatformFilter(platform)}
              >
                {platformLabel(platform)}{" "}
                <span>{items.filter((i) => i.assigned_platform === platform).length}</span>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {!board ? (
        <div className="loading-state"><LoaderCircle className="spin" /><span>Loading review queue…</span></div>
      ) : queue.length === 0 ? (
        <section className="panel empty-state">
          <h2>{filter === "needs_review" ? "Nothing to review" : "No clips here"}</h2>
          <p>
            {filter === "needs_review"
              ? "Generate a campaign, then approve Shorts, Reels, and posts here."
              : "Try another filter or platform."}
          </p>
        </section>
      ) : (
        <div className="review-grid">
          {queue.map((item) => {
            const status = String(item.status || "").toLowerCase();
            const reviewing = needsReviewStatus(item.status);
            const rejected = ["skipped", "rejected"].includes(status);
            const approved = status === "scheduled";
            return (
              <article className="review-card" key={item.id || `${item.assigned_platform}-${item.scheduled_date}`}>
                <div className="review-card-top">
                  <span className="cal-chip">
                    <BrandIcon platform={item.assigned_platform} size={14} label={item.assigned_platform} />
                    {platformLabel(item.assigned_platform)}
                  </span>
                  <span>{item.duration_seconds ? `${Math.round(item.duration_seconds)}s` : (item.play_url ? "Video" : "Copy")}</span>
                  {reviewing ? (
                    <div className="review-card-actions">
                      <button
                        className="secondary-button"
                        disabled={busy === item.id || !item.id}
                        onClick={() => setStatus(item.id, "skipped")}
                      >
                        {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <ThumbsDown size={16} />}
                        Reject
                      </button>
                      <button
                        className="primary-button"
                        disabled={busy === item.id || !item.id}
                        onClick={() => setStatus(item.id, "scheduled")}
                      >
                        {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <ThumbsUp size={16} />}
                        Approve
                      </button>
                    </div>
                  ) : rejected ? (
                    <div className="review-card-actions">
                      <button
                        className="secondary-button"
                        disabled={busy === item.id || !item.id}
                        onClick={() => setStatus(item.id, "ai_generated")}
                      >
                        {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
                        Restore
                      </button>
                      <button
                        className="primary-button"
                        disabled={busy === item.id || !item.id}
                        onClick={() => setStatus(item.id, "scheduled")}
                      >
                        {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <ThumbsUp size={16} />}
                        Approve
                      </button>
                    </div>
                  ) : approved ? (
                    <div className="review-card-actions">
                      <button
                        className="secondary-button"
                        disabled={busy === item.id || !item.id}
                        onClick={() => setStatus(item.id, "ai_generated")}
                      >
                        {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <Sparkles size={16} />}
                        Undo
                      </button>
                      <span>{String(item.status || "").replaceAll("_", " ")}</span>
                    </div>
                  ) : (
                    <span>{String(item.status || "").replaceAll("_", " ")}</span>
                  )}
                </div>
                {item.play_url ? (
                  <div className="asset-video">
                    <video
                      controls
                      playsInline
                      preload="metadata"
                      src={apiUrl(item.play_url)}
                      onError={(e) => {
                        e.currentTarget.style.display = "none";
                        const fallback = e.currentTarget.parentElement?.querySelector(".video-fallback");
                        if (fallback) fallback.hidden = false;
                      }}
                    />
                    <div className="asset-placeholder video-fallback" hidden>
                      <Film size={28} />
                      <span>Video unavailable</span>
                    </div>
                  </div>
                ) : (
                  <div className="asset-placeholder"><Film size={28} /><span>Copy-only post</span></div>
                )}
                <div className="asset-body">
                  <h3>{item.display_hook || item.hook || "Untitled clip"}</h3>
                  <QualityChips item={item} />
                  {item.transcript_excerpt ? (
                    <blockquote className="review-excerpt">{item.transcript_excerpt}</blockquote>
                  ) : null}
                  <p className="asset-caption">{item.display_caption || item.summary || item.editor_note}</p>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
