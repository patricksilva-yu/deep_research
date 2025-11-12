(function () {
  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-text");
    const messages = document.getElementById("messages");

    // API endpoint - update this if your FastAPI runs on a different port
    const API_URL = "http://localhost:8000/orchestrator/plan";

    if (!form || !input || !messages) return;

    function addMessage(text, type) {
      const messageEl = document.createElement("div");
      messageEl.className = `message ${type}`;
      messageEl.innerHTML = text; // Use innerHTML to support formatted content
      messages.appendChild(messageEl);
      messages.scrollTop = messages.scrollHeight;
      return messageEl;
    }

    function formatFinalReport(report) {
      let html = '<div class="final-report">';

      // Executive Summary (removed mission restatement)
      html += `<h2>📋 Executive Summary</h2>`;
      html += `<p>${formatTextWithLinks(report.executive_summary)}</p>`;

      // Sections
      if (report.sections && report.sections.length > 0) {
        html += `<h3>📑 Detailed Findings</h3>`;
        report.sections.forEach((section, idx) => {
          html += `<div class="report-section">`;
          html += `<h4>${idx + 1}. ${escapeHtml(section.title)}</h4>`;
          html += `<p>${formatTextWithLinks(section.summary)}</p>`;

          if (section.supporting_points && section.supporting_points.length > 0) {
            html += `<ul>`;
            section.supporting_points.forEach(point => {
              // Convert URLs in text to clickable links
              const formattedPoint = formatTextWithLinks(point);
              html += `<li>${formattedPoint}</li>`;
            });
            html += `</ul>`;
          }
          html += `</div>`;
        });
      }

      // Recommended Actions
      if (report.recommended_actions && report.recommended_actions.length > 0) {
        html += `<h3>✅ Recommended Actions</h3>`;
        html += `<ul>`;
        report.recommended_actions.forEach(action => {
          html += `<li>${formatTextWithLinks(action)}</li>`;
        });
        html += `</ul>`;
      }

      // Quality Notes
      if (report.quality_notes) {
        html += `<h3>🔍 Quality Notes</h3>`;
        html += `<p>${formatTextWithLinks(report.quality_notes)}</p>`;
      }

      // Sources
      if (report.sources && report.sources.length > 0) {
        html += `<h3>📚 Sources</h3>`;
        html += `<ul class="sources-list">`;
        report.sources.forEach((source, idx) => {
          // Extract domain from URL for display
          let displayText = source;
          try {
            const url = new URL(source);
            displayText = url.hostname.replace('www.', '') + url.pathname.substring(0, 40);
            if (url.pathname.length > 40) displayText += '...';
          } catch (e) {
            // If not a valid URL, truncate the text
            displayText = source.length > 60 ? source.substring(0, 60) + '...' : source;
          }
          html += `<li><a href="${escapeHtml(source)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(source)}">[${idx + 1}] ${escapeHtml(displayText)}</a></li>`;
        });
        html += `</ul>`;
      }

      html += '</div>';
      return html;
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.textContent = text;
      return div.innerHTML;
    }

    function formatTextWithLinks(text) {
      // Regular expression to match URLs
      const urlRegex = /(https?:\/\/[^\s]+)/g;

      // Escape the text first
      let escaped = escapeHtml(text);

      // Find all URLs and replace them with shortened links
      escaped = escaped.replace(urlRegex, (url) => {
        // Remove HTML entities that escapeHtml might have added
        const cleanUrl = url.replace(/&amp;/g, '&');

        // Create a shortened display version
        let displayText = cleanUrl;
        try {
          const urlObj = new URL(cleanUrl);
          displayText = urlObj.hostname.replace('www.', '');
          const pathPart = urlObj.pathname.substring(0, 30);
          if (urlObj.pathname.length > 30) {
            displayText += pathPart + '...';
          } else {
            displayText += pathPart;
          }
        } catch (e) {
          // If URL parsing fails, just truncate
          displayText = cleanUrl.length > 50 ? cleanUrl.substring(0, 50) + '...' : cleanUrl;
        }

        return `<a href="${escapeHtml(cleanUrl)}" target="_blank" rel="noopener noreferrer" title="${escapeHtml(cleanUrl)}">${escapeHtml(displayText)}</a>`;
      });

      return escaped;
    }

    function formatResearchPlan(plan) {
      let html = '<div class="research-plan">';
      html += `<h3>🔬 Research Plan</h3>`;
      html += `<p><strong>Mission:</strong> ${escapeHtml(plan.mission)}</p>`;

      if (plan.tasks && plan.tasks.length > 0) {
        html += `<p><strong>Tasks to execute:</strong></p>`;
        html += `<ol>`;
        plan.tasks.forEach(task => {
          html += `<li>`;
          // Format task_id to "Task #" format
          const taskLabel = task.task_id.replace(/task_?(\d+)/i, 'Task $1');
          html += `<strong>${escapeHtml(taskLabel)}:</strong> ${escapeHtml(task.description)}`;
          html += `</li>`;
        });
        html += `</ol>`;
      }

      html += '</div>';
      return html;
    }

    async function submitQuery(query) {
      const submitButton = form.querySelector('button[type="submit"]');
      const originalButtonText = submitButton.textContent;

      try {
        // Disable input during processing
        input.disabled = true;
        submitButton.disabled = true;
        submitButton.textContent = "Processing...";

        // Add animated loading message
        const loadingHTML = `
          <div class="loading-container">
            <div class="loading-spinner"></div>
            <div class="loading-text">
              <p><strong>🔄 Deep Research in Progress...</strong></p>
              <p class="loading-steps">
                <span class="step">Planning research tasks</span>
                <span class="step">Searching the web</span>
                <span class="step">Verifying findings</span>
                <span class="step">Generating comprehensive report</span>
              </p>
            </div>
          </div>
        `;
        const statusMsg = addMessage(loadingHTML, "bot loading");

        const response = await fetch(API_URL, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ query: query }),
        });

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Remove status message
        statusMsg.remove();

        // Display the research plan first
        if (data.plan) {
          addMessage(formatResearchPlan(data.plan), "bot");
        }

        // Display the final report if available
        if (data.final_report) {
          addMessage("🎉 <strong>Research Complete!</strong> Here's your comprehensive report:", "bot");
          addMessage(formatFinalReport(data.final_report), "bot");
        } else {
          // If no final report, the orchestrator might not have executed yet
          addMessage("⏳ Research plan created. The orchestrator will now execute the tasks and generate your report...", "bot");
        }

      } catch (error) {
        console.error("Error calling API:", error);
        addMessage(`❌ Error: ${error.message}`, "bot");
      } finally {
        // Re-enable input
        input.disabled = false;
        submitButton.disabled = false;
        submitButton.textContent = originalButtonText;
        input.focus();
      }
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const text = (input.value || "").trim();
      if (!text) return;

      addMessage(escapeHtml(text), "user");
      input.value = "";

      submitQuery(text);
    });
  });
})();
