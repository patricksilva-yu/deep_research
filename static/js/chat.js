(function () {
  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-text");
    const messages = document.getElementById("messages");
    const conversationList = document.getElementById("conversation-list");
    const newChatBtn = document.getElementById("new-chat-btn");
    const contextMenu = document.getElementById("context-menu");
    const renameModal = document.getElementById("rename-modal");
    const renameCancelBtn = document.getElementById("rename-cancel");
    const renameConfirmBtn = document.getElementById("rename-confirm");
    const renameInput = document.getElementById("rename-input");
    const fileInput = document.getElementById("file-input");
    const filePreviewContainer = document.getElementById("file-preview-container");

    // API backend URL from page meta tag or fall back to default
    const API_BASE_URL = document.documentElement.getAttribute('data-api-base-url') || 'http://localhost:8000';
    const API_URL = `/api/orchestrator/plan`;  // Use Flask proxy for file uploads
    const CONVERSATIONS_API = `${API_BASE_URL}/conversations`;

    let currentConversationId = null;
    let conversationData = {}; // Cache for conversation data
    let selectedFiles = []; // Track selected files

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

    function getCsrfToken() {
      // Extract CSRF token from cookies
      const name = "csrf_token=";
      const decodedCookie = decodeURIComponent(document.cookie);
      const cookieArray = decodedCookie.split(';');
      for (let cookie of cookieArray) {
        cookie = cookie.trim();
        if (cookie.indexOf(name) === 0) {
          return cookie.substring(name.length);
        }
      }
      return null;
    }

    function groupConversationsByDate(conversations) {
      const today = new Date();
      const yesterday = new Date(today);
      yesterday.setDate(yesterday.getDate() - 1);
      const sevenDaysAgo = new Date(today);
      sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

      const groups = {
        today: [],
        yesterday: [],
        previous7days: [],
        older: []
      };

      conversations.forEach(conv => {
        const convDate = new Date(conv.created_at);
        const convDateOnly = new Date(convDate.getFullYear(), convDate.getMonth(), convDate.getDate());
        const todayOnly = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        const yesterdayOnly = new Date(yesterday.getFullYear(), yesterday.getMonth(), yesterday.getDate());

        if (convDateOnly.getTime() === todayOnly.getTime()) {
          groups.today.push(conv);
        } else if (convDateOnly.getTime() === yesterdayOnly.getTime()) {
          groups.yesterday.push(conv);
        } else if (convDate > sevenDaysAgo) {
          groups.previous7days.push(conv);
        } else {
          groups.older.push(conv);
        }
      });

      return groups;
    }

    async function loadConversations() {
      try {
        const csrfToken = getCsrfToken();
        const headers = {};
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        const response = await fetch(`${CONVERSATIONS_API}/?limit=50`, {
          method: "GET",
          headers: headers,
          credentials: 'include'
        });

        if (!response.ok) {
          throw new Error(`Failed to load conversations: ${response.status}`);
        }

        const conversations = await response.json();
        conversationData = {};
        conversations.forEach(conv => {
          conversationData[conv.id] = conv;
        });

        renderConversationList(conversations);
      } catch (error) {
        console.error("Error loading conversations:", error);
      }
    }

    function renderConversationList(conversations) {
      conversationList.innerHTML = '';
      const groups = groupConversationsByDate(conversations);

      const sections = [
        { label: 'Today', conversations: groups.today },
        { label: 'Yesterday', conversations: groups.yesterday },
        { label: 'Previous 7 Days', conversations: groups.previous7days },
        { label: 'Older', conversations: groups.older }
      ];

      sections.forEach(section => {
        if (section.conversations.length > 0) {
          const headerEl = document.createElement('div');
          headerEl.className = 'conversation-section-header';
          headerEl.textContent = section.label;
          conversationList.appendChild(headerEl);

          section.conversations.forEach(conv => {
            const itemEl = document.createElement('div');
            itemEl.className = 'conversation-item';
            if (conv.id === currentConversationId) {
              itemEl.classList.add('active');
            }
            itemEl.dataset.conversationId = conv.id;

            const titleEl = document.createElement('div');
            titleEl.className = 'conv-title';
            titleEl.textContent = conv.title;

            const menuBtn = document.createElement('button');
            menuBtn.className = 'conv-menu-btn';
            menuBtn.textContent = '⋯';
            menuBtn.addEventListener('click', (e) => showContextMenu(e, conv.id));

            itemEl.appendChild(titleEl);
            itemEl.appendChild(menuBtn);
            itemEl.addEventListener('click', () => selectConversation(conv.id));

            conversationList.appendChild(itemEl);
          });
        }
      });
    }

    async function createNewConversation() {
      try {
        const csrfToken = getCsrfToken();
        const headers = {
          "Content-Type": "application/json"
        };
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        const response = await fetch(CONVERSATIONS_API, {
          method: "POST",
          headers: headers,
          credentials: 'include',
          body: JSON.stringify({ title: "New Conversation" })
        });

        if (!response.ok) {
          throw new Error(`Failed to create conversation: ${response.status}`);
        }

        const newConversation = await response.json();
        conversationData[newConversation.id] = newConversation;

        await selectConversation(newConversation.id);
        await loadConversations();
      } catch (error) {
        console.error("Error creating conversation:", error);
        addMessage(`❌ Error creating conversation: ${error.message}`, "bot");
      }
    }

    async function selectConversation(conversationId) {
      currentConversationId = conversationId;

      // Update UI
      document.querySelectorAll('.conversation-item').forEach(item => {
        item.classList.remove('active');
        if (parseInt(item.dataset.conversationId) === conversationId) {
          item.classList.add('active');
        }
      });

      // Show chat container and hide empty state
      document.getElementById('chat-empty-state').style.display = 'none';
      document.getElementById('chat-container').style.display = 'flex';
      messages.innerHTML = '';

      try {
        await loadConversationMessages(conversationId);
      } catch (error) {
        console.error("Error loading messages:", error);
        addMessage(`❌ Error loading messages: ${error.message}`, "bot");
      }
    }

    async function loadConversationMessages(conversationId) {
      try {
        const csrfToken = getCsrfToken();
        const headers = {};
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        const response = await fetch(`${CONVERSATIONS_API}/${conversationId}/messages`, {
          method: "GET",
          headers: headers,
          credentials: 'include'
        });

        if (!response.ok) {
          throw new Error(`Failed to load messages: ${response.status}`);
        }

        const messageList = await response.json();
        messages.innerHTML = '';

        messageList.forEach(msg => {
          // Convert 'assistant' role to 'bot' for frontend display
          const displayRole = msg.role === 'assistant' ? 'bot' : msg.role;

          // Don't escape HTML for bot messages since they contain formatted content
          // Only escape user messages for security
          const content = msg.role === 'user' ? escapeHtml(msg.content) : msg.content;
          addMessage(content, displayRole);
        });
      } catch (error) {
        console.error("Error loading conversation messages:", error);
        throw error;
      }
    }

    function showContextMenu(e, conversationId) {
      e.stopPropagation();
      contextMenu.style.display = 'block';
      contextMenu.style.position = 'fixed';
      contextMenu.style.left = e.pageX + 'px';
      contextMenu.style.top = e.pageY + 'px';
      contextMenu.dataset.conversationId = conversationId;
    }

    async function deleteConversation(conversationId) {
      if (!confirm('Are you sure you want to delete this conversation?')) {
        return;
      }

      try {
        const csrfToken = getCsrfToken();
        const headers = {};
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        const response = await fetch(`${CONVERSATIONS_API}/${conversationId}`, {
          method: "DELETE",
          headers: headers,
          credentials: 'include'
        });

        if (!response.ok) {
          throw new Error(`Failed to delete conversation: ${response.status}`);
        }

        if (currentConversationId === conversationId) {
          currentConversationId = null;
          messages.innerHTML = '';
          document.getElementById('chat-empty-state').style.display = 'block';
          document.getElementById('chat-container').style.display = 'none';
        }

        delete conversationData[conversationId];
        await loadConversations();
      } catch (error) {
        console.error("Error deleting conversation:", error);
        addMessage(`❌ Error deleting conversation: ${error.message}`, "bot");
      }
    }

    function openRenameModal(conversationId) {
      const conv = conversationData[conversationId];
      renameInput.value = conv ? conv.title : '';
      renameModal.style.display = 'flex';
      renameModal.dataset.conversationId = conversationId;
      renameInput.focus();
    }

    async function renameConversation(conversationId, newTitle) {
      try {
        const csrfToken = getCsrfToken();
        const headers = {
          "Content-Type": "application/json"
        };
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        const response = await fetch(`${CONVERSATIONS_API}/${conversationId}/title`, {
          method: "PATCH",
          headers: headers,
          credentials: 'include',
          body: JSON.stringify({ title: newTitle })
        });

        if (!response.ok) {
          throw new Error(`Failed to rename conversation: ${response.status}`);
        }

        conversationData[conversationId].title = newTitle;
        await loadConversations();
      } catch (error) {
        console.error("Error renaming conversation:", error);
        addMessage(`❌ Error renaming conversation: ${error.message}`, "bot");
      }
    }

    async function saveMessageToConversation(conversationId, role, content) {
      try {
        const csrfToken = getCsrfToken();
        const headers = {
          "Content-Type": "application/json"
        };
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        // Convert 'bot' role to 'assistant' for backend compatibility
        const backendRole = role === 'bot' ? 'assistant' : role;

        await fetch(`${CONVERSATIONS_API}/${conversationId}/messages`, {
          method: "POST",
          headers: headers,
          credentials: 'include',
          body: JSON.stringify({
            role: backendRole,
            content: content,
            metadata: {}
          })
        });
      } catch (error) {
        console.error("Error saving message to conversation:", error);
      }
    }

    function renderFilePreviews() {
      filePreviewContainer.innerHTML = '';

      if (selectedFiles.length === 0) {
        filePreviewContainer.style.display = 'none';
        return;
      }

      filePreviewContainer.style.display = 'flex';

      selectedFiles.forEach((file, index) => {
        const preview = document.createElement('div');
        preview.className = 'file-preview-item';

        const icon = getFileIcon(file.type);
        const fileName = file.name.length > 20 ? file.name.substring(0, 17) + '...' : file.name;

        preview.innerHTML = `
          <span class="file-icon">${icon}</span>
          <span class="file-name" title="${escapeHtml(file.name)}">${escapeHtml(fileName)}</span>
          <button type="button" class="file-remove-btn" data-index="${index}">×</button>
        `;

        filePreviewContainer.appendChild(preview);
      });

      // Add event listeners for remove buttons
      document.querySelectorAll('.file-remove-btn').forEach(btn => {
        btn.addEventListener('click', function() {
          const index = parseInt(this.dataset.index);
          selectedFiles.splice(index, 1);
          renderFilePreviews();
        });
      });
    }

    function getFileIcon(mimeType) {
      if (mimeType.startsWith('image/')) return '🖼️';
      if (mimeType === 'application/pdf') return '📄';
      if (mimeType.includes('spreadsheet') || mimeType.includes('excel')) return '📊';
      if (mimeType.includes('text')) return '📝';
      return '📎';
    }

    async function submitQuery(query) {
      const submitButton = form.querySelector('button[type="submit"]');
      const originalButtonText = submitButton.textContent;

      try {
        // Disable input during processing
        input.disabled = true;
        submitButton.disabled = true;
        fileInput.disabled = true;
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

        const csrfToken = getCsrfToken();
        const headers = {};
        if (csrfToken) {
          headers["X-CSRF-Token"] = csrfToken;
        }

        // Build FormData for multipart request
        const formData = new FormData();
        formData.append('query', query);

        if (currentConversationId) {
          formData.append('conversation_id', currentConversationId);
        }

        // Add files to FormData
        selectedFiles.forEach(file => {
          console.log(`Attaching file: ${file.name}, size: ${file.size} bytes`);
          formData.append('files', file);
        });

        console.log(`Sending request to ${API_URL} with ${selectedFiles.length} file(s)`);
        console.log('Headers:', headers);
        console.log('FormData entries:', Array.from(formData.entries()).map(([k, v]) => `${k}: ${v instanceof File ? v.name : v}`));

        const response = await fetch(API_URL, {
          method: "POST",
          headers: headers,
          credentials: 'include',
          body: formData
        }).catch(err => {
          console.error('Fetch threw an error:', err);
          throw err;
        });

        console.log('Fetch completed, got response');

        if (!response.ok) {
          const errorData = await response.json().catch(() => ({}));
          throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        // Remove status message
        statusMsg.remove();

        // Display the research plan first
        if (data.plan) {
          const planHtml = formatResearchPlan(data.plan);
          addMessage(planHtml, "bot");
          if (currentConversationId) {
            await saveMessageToConversation(currentConversationId, "bot", planHtml);
          }
        }

        // Display the final report if available
        if (data.final_report) {
          addMessage("🎉 <strong>Research Complete!</strong> Here's your comprehensive report:", "bot");
          const reportHtml = formatFinalReport(data.final_report);
          addMessage(reportHtml, "bot");
          if (currentConversationId) {
            await saveMessageToConversation(currentConversationId, "bot", reportHtml);
          }
        } else {
          // If no final report, the orchestrator might not have executed yet
          const infoMsg = "⏳ Research plan created. The orchestrator will now execute the tasks and generate your report...";
          addMessage(infoMsg, "bot");
          if (currentConversationId) {
            await saveMessageToConversation(currentConversationId, "bot", infoMsg);
          }
        }

      } catch (error) {
        console.error("Error calling API:", error);
        const errorMsg = `❌ Error: ${error.message}`;
        addMessage(errorMsg, "bot");
        if (currentConversationId) {
          await saveMessageToConversation(currentConversationId, "bot", errorMsg);
        }
      } finally {
        // Re-enable input
        input.disabled = false;
        submitButton.disabled = false;
        fileInput.disabled = false;
        submitButton.textContent = originalButtonText;

        // Clear selected files
        selectedFiles = [];
        fileInput.value = '';
        renderFilePreviews();

        input.focus();
      }
    }

    // Event listeners
    newChatBtn.addEventListener('click', createNewConversation);

    // File input change listener
    fileInput.addEventListener('change', function(event) {
      const files = Array.from(event.target.files);
      selectedFiles = selectedFiles.concat(files);
      renderFilePreviews();
    });

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const text = (input.value || "").trim();
      if (!text) return;

      if (!currentConversationId) {
        addMessage("❌ Please create or select a conversation first", "bot");
        return;
      }

      addMessage(escapeHtml(text), "user");
      saveMessageToConversation(currentConversationId, "user", text);
      input.value = "";

      submitQuery(text);
    });

    // Context menu event listeners
    document.addEventListener('click', function(e) {
      if (!e.target.closest('.conv-menu-btn')) {
        contextMenu.style.display = 'none';
      }
    });

    contextMenu.querySelectorAll('.menu-item').forEach(btn => {
      btn.addEventListener('click', async function() {
        const action = this.dataset.action;
        const conversationId = parseInt(contextMenu.dataset.conversationId);
        contextMenu.style.display = 'none';

        if (action === 'delete') {
          await deleteConversation(conversationId);
        } else if (action === 'rename') {
          openRenameModal(conversationId);
        } else if (action === 'share') {
          alert('Share functionality coming soon!');
        }
      });
    });

    renameCancelBtn.addEventListener('click', function() {
      renameModal.style.display = 'none';
    });

    renameConfirmBtn.addEventListener('click', async function() {
      const conversationId = parseInt(renameModal.dataset.conversationId);
      const newTitle = renameInput.value.trim();

      if (!newTitle) {
        alert('Please enter a title');
        return;
      }

      await renameConversation(conversationId, newTitle);
      renameModal.style.display = 'none';
    });

    renameInput.addEventListener('keypress', async function(e) {
      if (e.key === 'Enter') {
        renameConfirmBtn.click();
      }
    });

    // Load conversations on page load
    loadConversations();
  });
})();
