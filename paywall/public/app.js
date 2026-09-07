(() => {
  const toast = document.getElementById("toast");
  const year = document.querySelector("[data-year]");
  if (year) year.textContent = String(new Date().getFullYear());

  const nav = document.getElementById("nav-links");
  document.querySelector("[data-menu]")?.addEventListener("click", () => {
    nav?.classList.toggle("open");
  });
  nav?.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => nav.classList.remove("open"));
  });

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (!reduceMotion && "IntersectionObserver" in window) {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-visible");
            observer.unobserve(entry.target);
          }
        });
      },
      { rootMargin: "0px 0px -8% 0px", threshold: 0.12 }
    );
    document.querySelectorAll(".reveal").forEach((node) => observer.observe(node));
  } else {
    document.querySelectorAll(".reveal").forEach((node) => node.classList.add("is-visible"));
  }

  let interval = "month";
  const toggle = document.querySelector(".bill-toggle");
  const applyInterval = () => {
    document.querySelectorAll("[data-price-month]").forEach((node) => {
      node.textContent = node.getAttribute(interval === "year" ? "data-price-year" : "data-price-month");
    });
    document.querySelectorAll("[data-cadence]").forEach((node) => {
      node.textContent = interval === "year" ? "/ month, billed yearly" : "/ month";
    });
    document.querySelectorAll("[data-billed-year]").forEach((node) => {
      node.textContent = interval === "year" ? node.getAttribute("data-billed-year") : "Billed monthly";
    });
    toggle?.querySelectorAll("button").forEach((btn) => {
      btn.classList.toggle("on", btn.dataset.interval === interval);
    });
  };
  toggle?.querySelectorAll("button").forEach((btn) => {
    btn.addEventListener("click", () => {
      interval = btn.dataset.interval === "year" ? "year" : "month";
      applyInterval();
    });
  });

  const showToast = (message) => {
    if (!toast) return;
    toast.hidden = false;
    toast.textContent = message;
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => {
      toast.hidden = true;
    }, 5200);
  };

  const setBusy = (button, busy) => {
    button.disabled = busy;
    button.dataset.label = button.dataset.label || button.textContent;
    button.textContent = busy ? "Redirecting to Stripe…" : button.dataset.label;
  };

  document.querySelectorAll("[data-checkout]").forEach((button) => {
    button.addEventListener("click", async () => {
      setBusy(button, true);
      try {
        const res = await fetch("/api/checkout", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ plan: button.dataset.checkout, interval }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || !data.url) {
          throw new Error(data.error || "Checkout could not start.");
        }
        window.location.href = data.url;
      } catch (error) {
        showToast(error.message);
        setBusy(button, false);
      }
    });
  });
})();
