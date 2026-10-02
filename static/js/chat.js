(() => {
  const form = document.querySelector('#chat-form');
  const input = document.querySelector('#message-input');
  const messageList = document.querySelector('#message-list');
  const conversation = document.querySelector('#conversation');
  const typingIndicator = document.querySelector('#typing-indicator');
  const quickStart = document.querySelector('#quick-start');
  const sendButton = form.querySelector('button[type="submit"]');
  const modeButtons = document.querySelectorAll('.mode-button');
  const storyButton = document.querySelector('#story-button');
  const conversationId = Number(document.querySelector('.chat-content').dataset.conversationId);
  const historyPanel = document.querySelector('#conversation-history');
  const historyToggle = document.querySelector('#history-toggle');
  const memoryStatus = document.querySelector('#memory-status');
  const safetyBanner = document.querySelector('#safety-banner');

  let selectedMode = 'talk';

  function setMemoryStatus(message, isError = false) {
    memoryStatus.textContent = message;
    memoryStatus.classList.toggle('error', isError);
  }

  function showSafetyBanner(data) {
    if (!data || !data.triggered) {
      safetyBanner.hidden = true;
      return;
    }
    safetyBanner.hidden = false;
  }

  function addMessage(text, role) {
    const row = document.createElement('article');
    row.className = `message-row ${role === 'assistant' ? 'assistant-row' : 'user-row'}`;

    if (role === 'assistant') {
      const avatar = document.createElement('span');
      avatar.className = 'message-avatar';
      avatar.setAttribute('aria-hidden', 'true');
      avatar.textContent = 'S';
      row.append(avatar);
    }

    const content = document.createElement('div');
    content.className = 'message-content';

    if (role === 'assistant') {
      const name = document.createElement('span');
      name.className = 'message-name';
      name.textContent = 'SAATHI';
      content.append(name);
    }

    const bubble = document.createElement('div');
    bubble.className = `bubble ${role === 'assistant' ? 'assistant-bubble' : 'user-bubble'}`;
    bubble.textContent = text;
    content.append(bubble);
    row.append(content);

    if (role === 'user') {
      const actions = document.createElement('div');
      actions.className = 'message-actions';
      const rememberButton = document.createElement('button');
      rememberButton.type = 'button';
      rememberButton.className = 'remember-button';
      rememberButton.textContent = '🧠 Remember this';
      rememberButton.addEventListener('click', async () => {
        try {
          const response = await fetch('/api/memories/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ content: text, category: 'interest' })
          });
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) {
            throw new Error(payload.error || 'Could not save this memory.');
          }
          setMemoryStatus(payload.message || 'Got it — I\'ll remember that.');
        } catch (error) {
          setMemoryStatus(error.message || 'Could not save memory.', true);
        }
      });
      actions.append(rememberButton);
      row.append(actions);
    }

    messageList.append(row);
    scrollToLatest();
  }

  function scrollToLatest() {
    requestAnimationFrame(() => {
      conversation.scrollTop = conversation.scrollHeight;
    });
  }

  function setTyping(isTyping) {
    typingIndicator.hidden = !isTyping;
    sendButton.disabled = isTyping;
    if (isTyping) scrollToLatest();
  }

  async function respondTo(message, kind) {
    setTyping(true);
    try {
      const request = fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          conversation_id: conversationId,
          message,
          mode: selectedMode,
          kind
        })
      });
      const [result] = await Promise.all([
        request,
        new Promise((resolve) => window.setTimeout(resolve, 350))
      ]);
      const data = await result.json().catch(() => ({}));
      if (!result.ok) {
        throw new Error(data.error || 'Your message could not be saved. Please try again.');
      }
      addMessage(data.reply.content, 'assistant');
      showSafetyBanner(data.safety);
    } catch (error) {
      addMessage(error.message || 'Your message could not be saved. Please try again.', 'assistant');
    } finally {
      setTyping(false);
      input.focus();
    }
  }

  function sendMessage(message, kind = 'message') {
    const cleanMessage = message.trim();
    if (!cleanMessage || sendButton.disabled) return;

    addMessage(cleanMessage, 'user');
    input.value = '';
    input.style.height = 'auto';
    quickStart.hidden = true;
    respondTo(cleanMessage, kind);
  }

  form.addEventListener('submit', (event) => {
    event.preventDefault();
    sendMessage(input.value);
  });

  input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      form.requestSubmit();
    }
  });

  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = `${Math.min(input.scrollHeight, 120)}px`;
  });

  document.querySelectorAll('.prompt-chip').forEach((button) => {
    button.addEventListener('click', () => sendMessage(button.textContent));
  });

  modeButtons.forEach((button) => {
    button.addEventListener('click', () => {
      selectedMode = button.dataset.mode;
      modeButtons.forEach((modeButton) => {
        const isSelected = modeButton === button;
        modeButton.classList.toggle('is-active', isSelected);
        modeButton.setAttribute('aria-pressed', String(isSelected));
      });
      input.focus();
    });
  });

  storyButton.addEventListener('click', () => {
    sendMessage('Tell me a story', 'story');
  });

  historyToggle.addEventListener('click', () => {
    const isOpen = historyPanel.classList.toggle('is-open');
    historyToggle.setAttribute('aria-expanded', String(isOpen));
  });

  document.addEventListener('click', (event) => {
    if (!historyPanel.contains(event.target) && !historyToggle.contains(event.target)) {
      historyPanel.classList.remove('is-open');
      historyToggle.setAttribute('aria-expanded', 'false');
    }
  });

  if (messageList.dataset.hasMessages === 'true') scrollToLatest();

})();
