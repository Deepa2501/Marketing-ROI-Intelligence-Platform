/*
 * main.js — global application shell behavior, loaded on every page.
 * Handles sidebar collapse (desktop) / drawer (mobile), and the
 * dataset status indicator + campaign count badge in the topbar,
 * both driven by GET /api/summary.
 */

document.addEventListener("DOMContentLoaded", () => {
  initSidebar();
  loadDatasetStatus();
});

function initSidebar() {
  const shell = document.getElementById("app-shell");
  const sidebar = document.getElementById("sidebar");
  const backdrop = document.getElementById("sidebar-backdrop");
  const menuToggle = document.getElementById("menu-toggle");
  const collapseBtn = document.getElementById("sidebar-collapse-btn");

  // Desktop collapse state persists across page loads within a tab.
  if (sessionStorage.getItem("sidebar-collapsed") === "1") {
    shell.classList.add("is-collapsed");
  }

  if (collapseBtn) {
    collapseBtn.addEventListener("click", () => {
      const collapsed = shell.classList.toggle("is-collapsed");
      sessionStorage.setItem("sidebar-collapsed", collapsed ? "1" : "0");
    });
  }

  function openDrawer() {
    sidebar.classList.add("is-open");
    backdrop.classList.add("is-visible");
    menuToggle.setAttribute("aria-expanded", "true");
  }
  function closeDrawer() {
    sidebar.classList.remove("is-open");
    backdrop.classList.remove("is-visible");
    menuToggle.setAttribute("aria-expanded", "false");
  }

  if (menuToggle) {
    menuToggle.addEventListener("click", () => {
      sidebar.classList.contains("is-open") ? closeDrawer() : openDrawer();
    });
  }
  if (backdrop) {
    backdrop.addEventListener("click", closeDrawer);
  }
  // Close the mobile drawer after choosing a page.
  document.querySelectorAll(".sidebar__link").forEach((link) => {
    link.addEventListener("click", closeDrawer);
  });
}

async function loadDatasetStatus() {
  const dot = document.getElementById("data-status-dot");
  const text = document.getElementById("data-status-text");
  const badgeText = document.getElementById("campaign-badge-text");

  try {
    const data = await apiFetch("/api/summary");
    if (data.status === "connected") {
      dot.classList.add("data-status__dot--good");
      text.textContent = "Live Dataset Connected";
      badgeText.textContent = formatCompactNumber(data.kpis.total_campaigns) + " Campaigns";
    } else {
      dot.classList.remove("data-status__dot--good");
      text.textContent = "Dataset connection pending";
      badgeText.textContent = "No data";
    }
  } catch (err) {
    dot.classList.remove("data-status__dot--good");
    text.textContent = "Dataset connection pending";
    badgeText.textContent = "No data";
  }
}
