(function () {
  document.addEventListener("DOMContentLoaded", function () {
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-text");
    const messages = document.getElementById("messages");

    if (!form || !input || !messages) return;

    function addMessage(text, type) {
      const messageEl = document.createElement("div");
      messageEl.className = `message ${type}`;
      messageEl.textContent = text;
      messages.appendChild(messageEl);
      messages.scrollTop = messages.scrollHeight;
    }

    form.addEventListener("submit", function (event) {
      event.preventDefault();
      const text = (input.value || "").trim();
      if (!text) return;

      addMessage(text, "user");
      input.value = "";

      setTimeout(function () {
        addMessage("...processing (Flask endpoint goes here)", "bot");
      }, 300);
    });
  });
})();
