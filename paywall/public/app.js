(() => {
  const year = document.querySelector("[data-year]");
  if (year) year.textContent = String(new Date().getFullYear());

  const DEFAULT_STUDIO = "/app/?mode=signup";

  async function wireStudioLinks() {
    let studioUrl =
      (typeof window !== "undefined" && window.__CREATOROS_STUDIO__)
      || DEFAULT_STUDIO;
    try {
      const res = await fetch("/api/config", { cache: "no-store" });
      if (res.ok) {
        const type = res.headers.get("content-type") || "";
        if (type.includes("application/json")) {
          const data = await res.json();
          if (data?.studioUrl) studioUrl = String(data.studioUrl);
        }
      }
    } catch {
      /* fall back */
    }
    studioUrl = String(studioUrl || DEFAULT_STUDIO).trim() || DEFAULT_STUDIO;
    // Never point CTAs at the landing itself or a bare /open-studio loop.
    if (
      !studioUrl
      || studioUrl === "/"
      || studioUrl === "/open-studio"
      || !/\/app\/?/i.test(studioUrl)
    ) {
      studioUrl = DEFAULT_STUDIO;
    }
    if (!/[?&]mode=/.test(studioUrl) && !/[?&]signup=/.test(studioUrl)) {
      studioUrl += (studioUrl.includes("?") ? "&" : "?") + "mode=signup";
    }

    document.querySelectorAll("[data-studio-link], a.studio-link, a[href='/open-studio'], a[href='/app'], a[href='/try'], a[href='/demo'], a[href='/trial'], a[href='/free-demo'], a[href='/signup'], a[href='/login']").forEach((link) => {
      link.setAttribute("href", studioUrl);
    });
  }

  wireStudioLinks();

  const nav = document.getElementById("nav-links");
  document.querySelector("[data-menu]")?.addEventListener("click", () => {
    nav?.classList.toggle("nav-links-open");
  });
  nav?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => nav.classList.remove("nav-links-open"));
  });

  const tabs = document.querySelectorAll(".format-tab");
  const cards = document.querySelectorAll(".filmstrip .proof-card");
  const endnote = document.querySelector(".proof-endnote");
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const format = tab.getAttribute("data-format");
      tabs.forEach((node) => {
        const on = node === tab;
        node.classList.toggle("format-tab-active", on);
        node.setAttribute("aria-selected", on ? "true" : "false");
      });
      cards.forEach((card) => {
        if (format === "All cuts") {
          card.classList.remove("dim");
          return;
        }
        card.classList.toggle("dim", card.getAttribute("data-kind") !== format);
      });
      if (endnote) {
        const label = format === "All cuts" ? "all cuts" : format.toLowerCase();
        endnote.innerHTML = `<span class="live-dot"></span> Showing ${label} from one long-form source`;
      }
    });
  });

  const faqItems = [
    {
      question: "Does creatorOS auto-publish without my permission?",
      answer:
        "Never. Every cut, caption, and date waits in your review calendar until you explicitly approve it.",
    },
    {
      question: "What video formats and links are supported?",
      answer:
        "Upload MP4 or MOV files up to 4GB, or paste a YouTube link. Podcast RSS feeds are supported too.",
    },
    {
      question: "Do I need to connect social accounts for the demo?",
      answer:
        "No. Your first run creates clips, copy, and a calendar for review without asking for social permissions.",
    },
    {
      question: "What exactly is free?",
      answer:
        "One full campaign generation is free per email. After you review that first month of content, pay to keep generating.",
    },
  ];

  const faqList = document.getElementById("faq-list");
  if (faqList) {
    let active = 0;
    const render = () => {
      faqList.innerHTML = faqItems
        .map((item, index) => {
          const open = active === index;
          return `
            <div class="faq-item${open ? " faq-item-open" : ""}">
              <button type="button" class="faq-question" aria-expanded="${open}" data-faq="${index}">
                <span><small>0${index + 1}</small>${item.question}</span>
                <svg class="faq-chevron" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                  <path d="m6 9 6 6 6-6" />
                </svg>
              </button>
              ${open ? `<p class="faq-answer">${item.answer}</p>` : ""}
            </div>
          `;
        })
        .join("");
      faqList.querySelectorAll("[data-faq]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const index = Number(btn.getAttribute("data-faq"));
          active = active === index ? null : index;
          render();
        });
      });
    };
    render();
  }
})();
