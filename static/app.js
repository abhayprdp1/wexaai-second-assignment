document.addEventListener("DOMContentLoaded", () => {
    // ── Tab Management ────────────────────────────────────────────────────────
    const tabs = document.querySelectorAll(".nav-btn");
    const contents = document.querySelectorAll(".tab-content");

    tabs.forEach(tab => {
        tab.addEventListener("click", () => {
            tabs.forEach(t => t.classList.remove("active"));
            contents.forEach(c => c.classList.remove("active"));

            tab.classList.add("active");
            document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
        });
    });

    // ── Search & autocomplete ──────────────────────────────────────────────────
    const searchInput = document.getElementById("search-input");
    const resultsDropdown = document.getElementById("search-results");
    const detailView = document.getElementById("detail-view");
    const welcomeView = document.getElementById("welcome-view");

    let debounceTimer;
    searchInput.addEventListener("input", () => {
        clearTimeout(debounceTimer);
        const query = searchInput.value.trim();
        if (query.length < 2) {
            resultsDropdown.classList.add("hidden");
            return;
        }

        debounceTimer = setTimeout(() => {
            fetch(`/api/search?q=${encodeURIComponent(query)}`)
                .then(res => res.json())
                .then(data => {
                    renderSearchResults(data);
                });
        }, 300);
    });

    // Close dropdown on outside click
    document.addEventListener("click", (e) => {
        if (!searchInput.contains(e.target) && !resultsDropdown.contains(e.target)) {
            resultsDropdown.classList.add("hidden");
        }
    });

    function renderSearchResults(data) {
        resultsDropdown.innerHTML = "";
        
        if (data.movies.length === 0 && data.actors.length === 0) {
            resultsDropdown.innerHTML = `<div class="search-section"><p class="meta">No results found</p></div>`;
            resultsDropdown.classList.remove("hidden");
            return;
        }

        let html = "";
        if (data.movies.length > 0) {
            html += `<div class="search-section">
                <div class="section-title">Movies</div>`;
            data.movies.forEach(m => {
                html += `<div class="search-item" data-type="movie" data-id="${m.id}">
                    <strong>${m.title}</strong> (${m.year})
                </div>`;
            });
            html += `</div>`;
        }

        if (data.actors.length > 0) {
            html += `<div class="search-section">
                <div class="section-title">Actors</div>`;
            data.actors.forEach(a => {
                html += `<div class="search-item" data-type="actor" data-id="${a.id}">
                    <strong>${a.name}</strong>
                </div>`;
            });
            html += `</div>`;
        }

        resultsDropdown.innerHTML = html;
        resultsDropdown.classList.remove("hidden");

        // Click handlers for autocomplete items
        document.querySelectorAll(".search-item").forEach(item => {
            item.addEventListener("click", () => {
                const type = item.dataset.type;
                const id = item.dataset.id;
                resultsDropdown.classList.add("hidden");
                searchInput.value = "";
                loadDetails(type, id);
            });
        });
    }

    function loadDetails(type, id) {
        welcomeView.classList.add("hidden");
        detailView.classList.remove("hidden");
        detailView.innerHTML = `<p class="meta">Loading details...</p>`;

        fetch(`/api/${type}/${id}`)
            .then(res => res.json())
            .then(data => {
                if (type === "movie") {
                    renderMovieDetails(data);
                } else {
                    renderActorDetails(data);
                }
            })
            .catch(err => {
                detailView.innerHTML = `<p class="rating-badge" style="background:rgba(239,68,68,0.1); border-color:rgb(239,68,68); color:rgb(239,68,68)">Error loading data. Is the database online?</p>`;
            });
    }

    function renderMovieDetails(data) {
        let castHtml = "";
        data.cast.forEach(c => {
            castHtml += `<div class="card-item" data-type="actor" data-id="${c.id}">
                <h4>${c.name}</h4>
                <p>as ${c.role || "Supporting Cast"}</p>
            </div>`;
        });

        let recHtml = "";
        data.recommendations.forEach(r => {
            recHtml += `<div class="card-item" data-type="movie" data-id="${r.id}">
                <h4>${r.title}</h4>
                <p>Graph Recommendation</p>
            </div>`;
        });

        detailView.innerHTML = `
            <div class="detail-header">
                <div class="title-area">
                    <h2>${data.title}</h2>
                    <p class="meta">${data.year} &bull; ${data.genres.join(", ")}</p>
                    ${data.director ? `<p class="meta" style="margin-top:0.4rem">Directed by: <strong>${data.director}</strong></p>` : ''}
                </div>
                <div class="rating-badge">★ ${data.rating.toFixed(1)}</div>
            </div>
            
            <div class="overview-area">
                <p>${data.overview || "No overview available."}</p>
            </div>

            <div class="section-header">Cast</div>
            <div class="grid">${castHtml || '<p class="meta">No cast members listed.</p>'}</div>

            ${recHtml ? `
                <div class="section-header">More Like This (Graph Recommendation)</div>
                <div class="grid">${recHtml}</div>
            ` : ''}
        `;

        // Rebind click handlers for actors and recommended movies
        bindGridClicks();
    }

    function renderActorDetails(data) {
        let moviesHtml = "";
        data.movies.forEach(m => {
            moviesHtml += `<div class="card-item" data-type="movie" data-id="${m.id}">
                <h4>${m.title}</h4>
                <p>${m.year} &bull; as ${m.role || "Cast"}</p>
            </div>`;
        });

        let costarHtml = "";
        data.costars.forEach(c => {
            costarHtml += `<div class="card-item" data-type="actor" data-id="${c.id}">
                <h4>${c.name}</h4>
                <p>Shared Projects: ${c.weight}</p>
            </div>`;
        });

        detailView.innerHTML = `
            <div class="detail-header">
                <div class="title-area">
                    <h2>${data.name}</h2>
                    <p class="meta">${data.born ? `Born: ${data.born}` : 'Actor'}</p>
                </div>
            </div>

            <div class="section-header">Filmography</div>
            <div class="grid">${moviesHtml || '<p class="meta">No movies listed.</p>'}</div>

            <div class="section-header">Frequent Co-Stars (2-hop network)</div>
            <div class="grid">${costarHtml || '<p class="meta">No co-stars discovered.</p>'}</div>
        `;

        bindGridClicks();
    }

    function bindGridClicks() {
        document.querySelectorAll(".card-item").forEach(card => {
            card.addEventListener("click", () => {
                loadDetails(card.dataset.type, card.dataset.id);
                // Scroll to top of viewport
                window.scrollTo({ top: 0, behavior: 'smooth' });
            });
        });
    }

    // ── Degrees of Separation ─────────────────────────────────────────────────
    const findPathBtn = document.getElementById("find-path-btn");
    const actorStart = document.getElementById("actor-start");
    const actorEnd = document.getElementById("actor-end");
    const pathResults = document.getElementById("path-results");

    findPathBtn.addEventListener("click", () => {
        const start = actorStart.value.trim();
        const end = actorEnd.value.trim();

        if (!start || !end) {
            alert("Please enter both actor names.");
            return;
        }

        pathResults.classList.remove("hidden");
        pathResults.innerHTML = `<p class="meta">Tracing connection paths...</p>`;

        fetch(`/api/path?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`)
            .then(res => res.json())
            .then(data => {
                renderPath(data);
            })
            .catch(err => {
                pathResults.innerHTML = `<p class="meta">Error calculating separation.</p>`;
            });
    });

    function renderPath(data) {
        if (!data.nodes || data.nodes.length === 0) {
            pathResults.innerHTML = `
                <h3>No Connection Found</h3>
                <p class="meta" style="margin-top:0.5rem">We couldn't find a path between those two actors within our graph sample.</p>
            `;
            return;
        }

        let html = `<h3>Degrees of Separation Found</h3>`;
        html += `<div class="timeline" style="margin-top: 1.5rem;">`;

        for (let i = 0; i < data.nodes.length; i++) {
            const node = data.nodes[i];
            const isMovie = node.label === "Movie";
            const emoji = isMovie ? "🎬" : "👤";
            
            html += `
                <div class="timeline-node ${isMovie ? 'movie' : 'actor'}">
                    <div class="node-icon">${emoji}</div>
                    <div class="node-details">
                        <h4>${node.name}</h4>
                        <p>${node.label}</p>
                    </div>
                </div>
            `;

            // If there's a next node, render the connecting edge
            if (i < data.nodes.length - 1) {
                const rel = data.relationships[i];
                let label = rel.type === "ACTED_IN" ? "Acted in" : "Directed";
                if (rel.role) label += ` as "${rel.role}"`;
                
                // Adjust arrow direction based on layout context
                const directionSymbol = isMovie ? "←" : "→";

                html += `
                    <div class="timeline-edge">
                        ${directionSymbol} ${label}
                    </div>
                `;
            }
        }

        html += `</div>`;
        pathResults.innerHTML = html;
    }
});
