import { Image, LoaderCircle, Upload, X } from "lucide-react";
import { apiUrl } from "./api";

export const END_SCREEN_TEMPLATES = [
  { id: "logo_name", label: "Logo + Name" },
  { id: "logo_name_website", label: "Logo + Name + Website" },
  { id: "logo_cta", label: "Logo + CTA" },
];

export const END_SCREEN_DURATIONS = [2, 3, 4, 5];

export function formFromBrand(brand = {}) {
  return {
    brandName: brand.brand_name || "",
    website: brand.website || "",
    tagline: brand.tagline || "",
    endScreenEnabled: Boolean(brand.end_screen_enabled),
    endScreenDuration: brand.end_screen_duration || 3,
    endScreenTemplate: brand.end_screen_template || "logo_name_website",
    endScreenCta: brand.end_screen_cta || "",
    onScreenCaptionsEnabled: brand.on_screen_captions_enabled !== false,
    hasLogo: Boolean(brand.has_logo),
    logoCache: Date.now(),
    logoName: "",
    logoPreview: "",
  };
}

export function brandPayloadFromForm(value) {
  return {
    brand_name: value.brandName,
    website: value.website,
    tagline: value.tagline || "",
    end_screen_enabled: Boolean(value.endScreenEnabled),
    end_screen_duration: Number(value.endScreenDuration || 3),
    end_screen_template: value.endScreenTemplate || "logo_name_website",
    end_screen_cta: value.endScreenCta || "",
    on_screen_captions_enabled: Boolean(value.onScreenCaptionsEnabled),
  };
}

export function brandLogoSrc(hasLogo, cacheKey) {
  if (!hasLogo) return "";
  return apiUrl(`/brand/logo?t=${cacheKey || 1}`);
}

function shortTagline(text, maxChars = 72) {
  const cleaned = String(text || "").trim().replace(/\s+/g, " ");
  if (!cleaned) return "";
  const sentence = cleaned.split(/[.!?…]\s+/)[0].trim();
  const candidate = sentence || cleaned;
  if (candidate.length <= maxChars) return candidate;
  const words = candidate.split(" ");
  const out = [];
  for (const word of words) {
    const trial = [...out, word].join(" ");
    if (trial.length > maxChars - 1) break;
    out.push(word);
  }
  return out.length ? `${out.join(" ")}…` : `${candidate.slice(0, maxChars - 1)}…`;
}

function displayWebsite(url) {
  return String(url || "").replace(/^https?:\/\//i, "").replace(/\/$/, "");
}

export function EndScreenPreview({
  brandName,
  website,
  tagline,
  cta,
  template,
  logoSrc,
  duration = 3,
}) {
  const name = (brandName || "").trim() || "Your brand";
  const site = displayWebsite(website);
  const line = shortTagline(tagline);
  const call = (cta || "").trim();
  let secondary = "";
  let tertiary = "";
  if (template === "logo_name") {
    secondary = line;
  } else if (template === "logo_cta") {
    secondary = call || (site ? `Learn more → ${site}` : line);
  } else {
    secondary = line;
    tertiary = site;
  }

  return (
    <div className="end-screen-preview-wrap">
      <div className="end-screen-preview" aria-label="End screen preview">
        {logoSrc ? (
          <img src={logoSrc} alt="" className="end-screen-logo" />
        ) : (
          <div className="end-screen-logo placeholder">
            <Image size={22} />
          </div>
        )}
        <strong>{name}</strong>
        <span className="end-screen-divider" aria-hidden="true" />
        {secondary ? <span className="end-screen-tag">{secondary}</span> : null}
        {tertiary ? <span className="end-screen-web">{tertiary}</span> : null}
      </div>
      <small>{duration}s appended after each Short / Reel</small>
    </div>
  );
}

export function BrandingFields({
  value,
  onChange,
  logoUploading,
  onLogoUpload,
  onClearLogo,
  compact = false,
}) {
  const update = (key, next) => onChange({ ...value, [key]: next });
  const logoSrc = value.logoPreview || brandLogoSrc(value.hasLogo, value.logoCache);

  return (
    <div className={`branding-fields ${compact ? "compact" : ""}`}>
      <div className="branding-toggle-row">
        <div>
          <strong>Burn on-screen captions into Shorts / Reels</strong>
          <p>Uses Whisper word timing (not Gemini). Great for muted autoplay; turn off for a cleaner look.</p>
        </div>
        <button
          type="button"
          className={`toggle ${value.onScreenCaptionsEnabled ? "on" : ""}`}
          onClick={() => update("onScreenCaptionsEnabled", !value.onScreenCaptionsEnabled)}
          aria-label={value.onScreenCaptionsEnabled ? "Disable on-screen captions" : "Enable on-screen captions"}
        >
          <span />
        </button>
      </div>

      <div className="branding-toggle-row">
        <div>
          <strong>Add end screen to generated videos</strong>
          <p>Appends your logo and name after every Short, Reel, and TikTok — not over the clip.</p>
        </div>
        <button
          type="button"
          className={`toggle ${value.endScreenEnabled ? "on" : ""}`}
          onClick={() => update("endScreenEnabled", !value.endScreenEnabled)}
          aria-label={value.endScreenEnabled ? "Disable end screen" : "Enable end screen"}
        >
          <span />
        </button>
      </div>

      <div className="form-grid branding-grid">
        <label className="field wide">
          <span>Logo</span>
          <label className={`upload-drop logo-drop ${logoUploading ? "busy" : ""}`}>
            {logoSrc ? <img src={logoSrc} alt="" className="logo-thumb" /> : <Image size={26} />}
            <div>
              <strong>{value.logoName || (value.hasLogo ? "Replace logo" : "Upload logo")}</strong>
              <span>{logoUploading ? "Uploading…" : "PNG, JPG, or WebP. Transparent PNG works best."}</span>
            </div>
            {logoUploading ? <LoaderCircle className="spin" /> : <Upload size={19} />}
            <input
              type="file"
              accept="image/png,image/jpeg,image/webp,.png,.jpg,.jpeg,.webp"
              onChange={(e) => onLogoUpload(e.target.files?.[0])}
            />
          </label>
          {value.hasLogo ? (
            <button type="button" className="text-button logo-clear" onClick={onClearLogo}>
              <X size={14} /> Remove logo
            </button>
          ) : null}
        </label>
        <label className="field">
          <span>Brand name</span>
          <input
            value={value.brandName}
            onChange={(e) => update("brandName", e.target.value)}
            placeholder="Radiant Minds"
          />
          {value.endScreenEnabled && !String(value.brandName || "").trim() ? (
            <small className="field-error">Brand name is required for the end screen.</small>
          ) : null}
        </label>
        <label className="field">
          <span>Website</span>
          <input
            value={value.website}
            onChange={(e) => update("website", e.target.value)}
            placeholder="radiantmindsma.com"
          />
        </label>
        <label className="field">
          <span>Tagline</span>
          <input
            value={value.tagline}
            onChange={(e) => update("tagline", e.target.value)}
            placeholder="Learn. Grow. Thrive."
          />
          <small>Keep this short — long quotes get trimmed on the end screen.</small>
        </label>
        <label className="field">
          <span>CTA</span>
          <input
            value={value.endScreenCta}
            onChange={(e) => update("endScreenCta", e.target.value)}
            placeholder="Learn more →"
          />
        </label>
        <label className="field">
          <span>Duration</span>
          <select
            value={value.endScreenDuration}
            onChange={(e) => update("endScreenDuration", Number(e.target.value))}
          >
            {END_SCREEN_DURATIONS.map((sec) => (
              <option key={sec} value={sec}>{sec} seconds</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Template</span>
          <select
            value={value.endScreenTemplate}
            onChange={(e) => update("endScreenTemplate", e.target.value)}
          >
            {END_SCREEN_TEMPLATES.map((item) => (
              <option key={item.id} value={item.id}>{item.label}</option>
            ))}
          </select>
        </label>
      </div>

      <EndScreenPreview
        brandName={value.brandName}
        website={value.website}
        tagline={value.tagline}
        cta={value.endScreenCta}
        template={value.endScreenTemplate}
        logoSrc={logoSrc}
        duration={value.endScreenDuration}
      />
    </div>
  );
}
