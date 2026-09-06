import { useEffect, useMemo, useState } from "react";
import {
  Copy,
  Download,
  FileText,
  Link2,
  LoaderCircle,
  Search,
  Sparkles,
} from "lucide-react";
import { apiUrl, creatorApi } from "./api";

function formatTime(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  return `${m}:${String(s).padStart(2, "0")}`;
}

export function TranscriptPage({ AppShell, PageHeading, Notice, CopyButton, Field }) {
  const [data, setData] = useState(null);
  const [clipMeta, setClipMeta] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [query, setQuery] = useState("");
  const [url, setUrl] = useState("");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [mode, setMode] = useState("range"); // range | full

  const loadExisting = () => {
    setLoading(true);
    creatorApi
      .transcript()
      .then(setData)
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadExisting();
  }, []);

  const segments = data?.segments || [];
  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return segments;
    return segments.filter((seg) => String(seg.text || "").toLowerCase().includes(q));
  }, [segments, query]);

  const runDownload = async () => {
    setBusy("download");
    setError("");
    try {
      const meta = await creatorApi.fetchClip({
        url,
        start: start || undefined,
        end: end || undefined,
      });
      setClipMeta(meta);
      setData((prev) => ({
        ...(prev || {}),
        play_url: meta.play_url,
        download_url: meta.download_url,
        timespan_label: meta.timespan_label,
        job_id: meta.job_id,
        kind: "clip_desk",
      }));
    } catch (err) {
      setError(err.message || "Download failed.");
    } finally {
      setBusy("");
    }
  };

  const runTranscribe = async () => {
    setBusy("transcribe");
    setError("");
    try {
      const result = await creatorApi.transcribeClip({
        url: url || undefined,
        start: mode === "range" ? (start || undefined) : undefined,
        end: mode === "range" ? (end || undefined) : undefined,
        mode,
        job_id: clipMeta?.job_id || undefined,
      });
      setClipMeta((prev) => ({
        ...(prev || {}),
        job_id: result.job_id,
        play_url: result.play_url,
        download_url: result.download_url,
        timespan_label: result.timespan_label,
      }));
      setData(result);
    } catch (err) {
      setError(err.message || "Transcription failed.");
    } finally {
      setBusy("");
    }
  };

  const FieldBox = Field || (({ label, hint, children, wide }) => (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {hint ? <small>{hint}</small> : null}
      {children}
    </label>
  ));

  return (
    <AppShell flow={false}>
      <PageHeading
        eyebrow="Editor tools"
        title="Clip & transcript desk"
        description="Paste a link, set an optional timespan, download only that part, and transcribe the full video or just the range you need — no full campaign required."
        aside={
          data?.transcript ? (
            <CopyButton text={data.transcript} label="Copy transcript" />
          ) : null
        }
      />
      {error ? <Notice>{error}</Notice> : null}

      <section className="panel campaign-panel clip-desk-panel">
        <div className="section-heading">
          <div>
            <span className="overline">Standalone fetch</span>
            <h2>URL + timespan</h2>
          </div>
          <Sparkles size={18} />
        </div>
        <p className="account-copy">
          Example: 2-hour podcast → start <code>12:00</code>, end <code>25:30</code> → only that window downloads.
          Then choose full-video transcript or just that part.
        </p>

        <FieldBox label="Video URL" hint="YouTube / podcast URL you have rights to use" wide>
          <div className="input-with-icon">
            <Link2 size={18} />
            <input
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              placeholder="https://youtube.com/watch?v=…"
            />
          </div>
        </FieldBox>

        <div className="form-grid timespan-grid">
          <FieldBox label="Start (optional)" hint="e.g. 12:00 or 720">
            <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="0:00" />
          </FieldBox>
          <FieldBox label="End (optional)" hint="e.g. 25:30 — leave blank for end of video">
            <input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="25:30" />
          </FieldBox>
        </div>

        <div className="clip-mode-row">
          <button
            type="button"
            className={mode === "range" ? "active" : ""}
            onClick={() => setMode("range")}
          >
            Transcribe timespan only
          </button>
          <button
            type="button"
            className={mode === "full" ? "active" : ""}
            onClick={() => setMode("full")}
          >
            Transcribe full video
          </button>
        </div>

        <div className="page-actions">
          <button
            className="secondary-button"
            disabled={Boolean(busy) || !url.trim()}
            onClick={runDownload}
          >
            {busy === "download" ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
            Download this part
          </button>
          <button
            className="primary-button"
            disabled={Boolean(busy) || (!url.trim() && !clipMeta?.job_id)}
            onClick={runTranscribe}
          >
            {busy === "transcribe" ? <LoaderCircle className="spin" size={16} /> : <FileText size={16} />}
            {mode === "full" ? "Download + full transcript" : "Download + transcript range"}
          </button>
        </div>
        <p className="source-legal-note">
          Full-video transcription on long podcasts can take several minutes. Prefer a timespan when you only need one section.
        </p>
      </section>

      {(clipMeta?.play_url || data?.play_url) ? (
        <section className="panel campaign-panel" style={{ marginTop: 18 }}>
          <div className="section-heading">
            <div>
              <span className="overline">Downloaded clip</span>
              <h2>{clipMeta?.timespan_label || data?.timespan_label || "Preview"}</h2>
            </div>
            <a
              className="secondary-button"
              href={apiUrl(clipMeta?.download_url || data?.download_url)}
              download
            >
              <Download size={16} /> Save MP4
            </a>
          </div>
          <div className="asset-video">
            <video
              key={clipMeta?.play_url || data?.play_url}
              controls
              preload="metadata"
              src={apiUrl(clipMeta?.play_url || data?.play_url)}
            />
          </div>
        </section>
      ) : null}

      {loading && !data ? (
        <div className="loading-state"><LoaderCircle className="spin" /><span>Loading transcript…</span></div>
      ) : !data?.segments?.length && !data?.transcript ? (
        <section className="panel home-empty" style={{ marginTop: 18 }}>
          <span className="overline">Transcript</span>
          <h2>Nothing here yet</h2>
          <p>Use the form above, or open a campaign transcript after a generate run.</p>
          <button className="secondary-button" onClick={loadExisting}>Refresh</button>
        </section>
      ) : (
        <>
          <div className="result-kpis" style={{ marginTop: 18 }}>
            <div><FileText size={19} /><span>Segments</span><strong>{data.segment_count ?? segments.length}</strong></div>
            <div><Search size={19} /><span>Matches</span><strong>{filtered.length}</strong></div>
            <div><Copy size={19} /><span>Duration</span><strong>{data.duration_seconds ? formatTime(data.duration_seconds) : "—"}</strong></div>
            <div><FileText size={19} /><span>Scope</span><strong>{data.mode === "full" ? "Full" : (data.timespan_label || data.kind || "—")}</strong></div>
          </div>

          <div className="transcript-toolbar">
            <label className="transcript-search">
              <Search size={16} />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search words spoken in the video…"
              />
            </label>
          </div>

          <section className="panel transcript-panel">
            <div className="transcript-list">
              {filtered.length === 0 ? (
                <p className="account-copy">No lines match “{query}”.</p>
              ) : (
                filtered.map((seg, index) => (
                  <article className="transcript-row" key={`${seg.start}-${index}`}>
                    <time>{formatTime(seg.start)}–{formatTime(seg.end)}</time>
                    <p>{seg.text}</p>
                  </article>
                ))
              )}
            </div>
          </section>
        </>
      )}
    </AppShell>
  );
}
