(() => {
  const runId = new URLSearchParams(location.search).get("run_id");
  const originalFetch = window.fetch.bind(window);
  let provideInitialSnapshot;
  const initialSnapshot = new Promise(resolve => { provideInitialSnapshot = resolve; });
  let hasInitialSnapshot = false;

  window.addEventListener("message", event => {
    if (event.origin !== location.origin || event.data?.type !== "management-referee-snapshot" ||
        event.data.run_id !== runId || !event.data.snapshot) return;
    if (!hasInitialSnapshot) {
      hasInitialSnapshot = true;
      provideInitialSnapshot(event.data.snapshot);
    }
    if (typeof window.updateBigvilleSnapshot === "function") {
      window.updateBigvilleSnapshot(event.data.snapshot);
    }
  });

  window.fetch = async (resource, options = {}) => {
    const path = typeof resource === "string" ? resource : resource.url;
    if (path === "/api/state") {
      if (!runId) throw new Error("Missing managed run ID.");
      const snapshot = await initialSnapshot;
      if (!snapshot) throw new Error("Referee snapshot was not provided by the management view.");
      return new Response(JSON.stringify(snapshot), {
        status: 200, headers: {"Content-Type": "application/json"},
      });
    }
    if (path === "/api/turn" || path === "/api/reset") {
      return new Response(JSON.stringify({error: "The management referee renderer is read only."}), {
        status: 403, headers: {"Content-Type": "application/json"},
      });
    }
    return originalFetch(resource, options);
  };
})();
