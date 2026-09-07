import { useEffect, useMemo, useState } from "react";
import {
  Copy,
  Download,
  FileText,
  Link2,
  LoaderCircle,
  Search,
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
  const [mode, setMode] = useState("range");

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

  const FieldBox = Field || (({ label, children, wide }) => (
    <label className={`field ${wide ? "wide" : ""}`}>
      <span>{label}</span>
      {children}
    </label>
  ));

  return (
    <AppShell flow={false}>
      <PageHeading
        title="Clip & transcript desk"
        description="Pull a section from a video, then download or transcribe it."
        aside={
          data?.transcript ? (
            <CopyButton text={data.transcript} label="Copy transcript" />
          ) : null
        }
      />
      {error ? <Notice>{error}</Notice> : null}

      <section className="panel clip-desk-steps">
        <div className="clip-step">
          <h2>1. Add your video</h2>
          <p>Paste a YouTube or podcast URL.</p>
          <FieldBox label="Video URL" wide>
            <div className="input-with-icon">
              <Link2 size={18} />
              <input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="https://youtube.com/watch?v=…"
              />
            </div>
          </FieldBox>
        </div>

        <div className="clip-step">
          <h2>2. Choose the section</h2>
          <p>Optional — leave blank to use the full video.</p>
          <div className="form-grid timespan-grid">
            <FieldBox label="Start time">
              <input value={start} onChange={(e) => setStart(e.target.value)} placeholder="0:00" />
            </FieldBox>
            <FieldBox label="End time">
              <input value={end} onChange={(e) => setEnd(e.target.value)} placeholder="25:30" />
            </FieldBox>
          </div>
        </div>

        <div className="clip-step">
          <h2>3. Choose what to do</h2>
          <div className="clip-mode-row">
            <button
              type="button"
              className={mode === "range" ? "active" : ""}
              onClick={() => setMode("range")}
            >
              Selection only
            </button>
            <button
              type="button"
              className={mode === "full" ? "active" : ""}
              onClick={() => setMode("full")}
            >
              Full video
            </button>
          </div>
          <div className="clip-actions">
            <button
              className="secondary-button"
              disabled={Boolean(busy) || !url.trim()}
              onClick={runDownload}
            >
              {busy === "download" ? <LoaderCircle className="spin" size={16} /> : <Download size={16} />}
              Download selection
            </button>
            <button
              className="primary-button"
              disabled={Boolean(busy) || (!url.trim() && !clipMeta?.job_id)}
              onClick={runTranscribe}
            >
              {busy === "transcribe" ? <LoaderCircle className="spin" size={16} /> : <FileText size={16} />}
              {mode === "full" ? "Transcribe full video" : "Transcribe selection"}
            </button>
          </div>
        </div>
      </section>

      {(clipMeta?.play_url || data?.play_url) ? (
        <section className="panel campaign-panel" style={{ marginTop: 18 }}>
          <div className="section-heading">
            <div>
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
        <section className="panel empty-state" style={{ marginTop: 18 }}>
          <h2>No transcript yet</h2>
          <p>Add a video above to download a clip or generate a transcript.</p>
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
                placeholder="Search transcript"
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
