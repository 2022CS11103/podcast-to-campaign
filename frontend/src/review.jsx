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
  return ["ai_generated", "pending", "draft", ""].includes(raw);
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
      {reasons.slice(0, 4).map((reason) => (
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

  const loadBoard = () =>
    creatorApi.board().then(setBoard).catch((err) => setError(err.message));

  useEffect(() => {
    loadBoard();
  }, []);

  const items = board?.items || [];
  const queue = useMemo(() => {
    if (filter === "all") return items;
    if (filter === "approved") {
      return items.filter((item) => String(item.status || "").toLowerCase() === "scheduled");
    }
    if (filter === "rejected") {
      return items.filter((item) => ["skipped", "rejected"].includes(String(item.status || "").toLowerCase()));
    }
    return items.filter((item) => needsReviewStatus(item.status));
  }, [items, filter]);

  const pendingCount = items.filter((item) => needsReviewStatus(item.status)).length;

  const setStatus = async (itemId, status) => {
    setBusy(itemId);
    setError("");
    try {
      await creatorApi.setPostStatus(itemId, status);
      await loadBoard();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  const bulk = async (action) => {
    setBusy(action);
    setError("");
    try {
      const ids = queue.filter((item) => needsReviewStatus(item.status)).map((item) => item.id);
      await creatorApi.reviewBulk({ action, item_ids: ids.length ? ids : undefined });
      await loadBoard();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  };

  return (
    <AppShell flow={false}>
      <PageHeading
        eyebrow="Human review"
        title="Approve clips before they go on the calendar"
        description="AI proposes candidates with a short reason each. You pick what ships — this is the agency desk, not set-and-forget auto-post."
        aside={
          <div className="heading-actions">
            <button className="secondary-button" onClick={() => bulk("reject")} disabled={Boolean(busy) || pendingCount === 0}>
              {busy === "reject" ? <LoaderCircle className="spin" size={16} /> : <ThumbsDown size={16} />}
              Reject queue
            </button>
            <button className="primary-button" onClick={() => bulk("approve")} disabled={Boolean(busy) || pendingCount === 0}>
              {busy === "approve" ? <LoaderCircle className="spin" size={16} /> : <ThumbsUp size={16} />}
              Approve all pending
            </button>
          </div>
        }
      />
      {error ? <Notice>{error}</Notice> : null}

      <div className="result-kpis">
        <div><Sparkles size={19} /><span>Needs approval</span><strong>{pendingCount}</strong></div>
        <div><Film size={19} /><span>Total assets</span><strong>{items.length || "—"}</strong></div>
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

      {!board ? (
        <div className="loading-state"><LoaderCircle className="spin" /><span>Loading review queue…</span></div>
      ) : queue.length === 0 ? (
        <section className="panel home-empty">
          <span className="overline">Review queue</span>
          <h2>{filter === "needs_review" ? "Nothing waiting for approval" : "No clips in this filter"}</h2>
          <p>
            {filter === "needs_review"
              ? "Generate a campaign, then come back here to approve what the agency would ship."
              : "Switch filters or run a new campaign."}
          </p>
        </section>
      ) : (
        <div className="review-grid">
          {queue.map((item) => (
            <article className="review-card" key={item.id}>
              <div className="review-card-top">
                <span className="cal-chip">
                  <BrandIcon platform={item.assigned_platform} size={14} label={item.assigned_platform} />
                  {(item.assigned_platform || "").replaceAll("_", " ")}
                </span>
                <span>{item.duration_seconds ? `${Math.round(item.duration_seconds)}s` : ""}</span>
              </div>
              {item.play_url ? (
                <div className="asset-video">
                  <video controls preload="metadata" src={apiUrl(item.play_url)} />
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
                <div className="page-actions">
                  <button
                    className="secondary-button"
                    disabled={busy === item.id}
                    onClick={() => setStatus(item.id, "skipped")}
                  >
                    {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <ThumbsDown size={16} />}
                    Reject
                  </button>
                  <button
                    className="primary-button"
                    disabled={busy === item.id}
                    onClick={() => setStatus(item.id, "scheduled")}
                  >
                    {busy === item.id ? <LoaderCircle className="spin" size={16} /> : <ThumbsUp size={16} />}
                    Approve
                  </button>
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </AppShell>
  );
}
