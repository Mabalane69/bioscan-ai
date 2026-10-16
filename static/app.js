const SESSION_KEY = 'bioscan_session';
const state = {
  token: sessionStorage.getItem(SESSION_KEY),
  user: null,
  contacts: [],
  searchTimer: null,
  searchSequence: 0,
  cameraStream: null
};

const elements = {
  authView: document.getElementById('auth-view'),
  dashboard: document.getElementById('dashboard'),
  accountActions: document.getElementById('account-actions'),
  signedInName: document.getElementById('signed-in-name'),
  authHeading: document.getElementById('auth-heading'),
  authDescription: document.getElementById('auth-description'),
  loginForm: document.getElementById('login-form'),
  registerForm: document.getElementById('register-form'),
  authMessage: document.getElementById('auth-message'),
  profileForm: document.getElementById('profile-form'),
  profileMessage: document.getElementById('profile-message'),
  peopleSearch: document.getElementById('people-search'),
  searchResults: document.getElementById('search-results'),
  contactForm: document.getElementById('contact-form'),
  selectedPerson: document.getElementById('selected-person'),
  familyMessage: document.getElementById('family-message'),
  contactsList: document.getElementById('contacts-list'),
  contactsEmpty: document.getElementById('contacts-empty'),
  contactsMessage: document.getElementById('contacts-message'),
  enrollmentForm: document.getElementById('face-enrollment-form'),
  enrollmentStatus: document.getElementById('face-enrollment-status'),
  enrollmentMessage: document.getElementById('enrollment-message'),
  removeFaceEnrollment: document.getElementById('remove-face-enrollment'),
  scanCamera: document.getElementById('scan-camera'),
  cameraPlaceholder: document.getElementById('camera-placeholder'),
  startCamera: document.getElementById('start-camera'),
  captureMatch: document.getElementById('capture-match'),
  matchImage: document.getElementById('match-image'),
  matchResult: document.getElementById('match-result'),
  scanMessage: document.getElementById('scan-message'),
  followRequests: document.getElementById('follow-requests-list'),
  followMessage: document.getElementById('follow-message'),
  viewedProfile: document.getElementById('viewed-profile'),
  viewedProfileDetails: document.getElementById('viewed-profile-details')
};

function formValues(form) {
  return Object.fromEntries(new FormData(form).entries());
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (state.token) headers.set('Authorization', `Bearer ${state.token}`);
  if (options.body !== undefined) headers.set('Content-Type', 'application/json');

  const response = await fetch(path, {
    ...options,
    headers,
    body: options.body === undefined ? undefined : JSON.stringify(options.body)
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && path !== '/api/login' && path !== '/api/register') {
      clearSession();
      showAuth();
    }
    throw new Error(data.error || 'The request could not be completed.');
  }
  return data;
}

function setMessage(element, message, isError = false) {
  element.textContent = message;
  element.classList.toggle('error', isError);
  element.classList.toggle('success', Boolean(message) && !isError);
}

function rememberSession(result) {
  state.token = result.token;
  state.user = result.user;
  sessionStorage.setItem(SESSION_KEY, result.token);
  showDashboard();
  loadDashboard();
}

function clearSession() {
  state.token = null;
  state.user = null;
  sessionStorage.removeItem(SESSION_KEY);
}

function showAuth(mode = 'login') {
  elements.authView.hidden = false;
  elements.dashboard.hidden = true;
  elements.accountActions.hidden = true;
  switchAuthMode(mode);
}

function switchAuthMode(mode) {
  const registering = mode === 'register';
  elements.loginForm.hidden = registering;
  elements.registerForm.hidden = !registering;
  document.getElementById('show-login').classList.toggle('active', !registering);
  document.getElementById('show-register').classList.toggle('active', registering);
  document.getElementById('show-login').setAttribute('aria-selected', String(!registering));
  document.getElementById('show-register').setAttribute('aria-selected', String(registering));
  elements.authHeading.textContent = registering ? 'Create your profile' : 'Welcome back';
  elements.authDescription.textContent = registering
    ? 'Register so your family can find and add you.'
    : 'Sign in to manage your profile and emergency list.';
  setMessage(elements.authMessage, '');
}

function showDashboard() {
  elements.authView.hidden = true;
  elements.dashboard.hidden = false;
  elements.accountActions.hidden = false;
  elements.signedInName.textContent = state.user.full_name;
  document.getElementById('welcome-heading').textContent = `Hello, ${state.user.full_name}`;

  const profile = elements.profileForm.elements;
  profile.full_name.value = state.user.full_name;
  profile.email.value = state.user.email;
  profile.phone.value = state.user.phone || '';
  profile.discoverable.checked = state.user.discoverable;
  elements.enrollmentStatus.textContent = state.user.face_search_enabled
    ? 'Enrolled · searchable'
    : 'Not enrolled';
  elements.removeFaceEnrollment.hidden = !state.user.face_search_enabled;
}

async function loadDashboard() {
  try {
    const [profileData, contactsData, followData] = await Promise.all([
      request('/api/me'),
      request('/api/contacts'),
      request('/api/follow-requests')
    ]);
    state.user = profileData.user;
    showDashboard();
    state.contacts = contactsData.contacts;
    renderContacts();
    renderFollowRequests(followData);
  } catch (error) {
    if (state.token) setMessage(elements.contactsMessage, error.message, true);
  }
}

document.getElementById('show-login').addEventListener('click', () => switchAuthMode('login'));
document.getElementById('show-register').addEventListener('click', () => switchAuthMode('register'));

elements.loginForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = formValues(elements.loginForm);
  try {
    rememberSession(await request('/api/login', { method: 'POST', body: values }));
    elements.loginForm.reset();
  } catch (error) {
    setMessage(elements.authMessage, error.message, true);
  }
});

elements.registerForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = formValues(elements.registerForm);
  values.discoverable = elements.registerForm.elements.discoverable.checked;
  try {
    rememberSession(await request('/api/register', { method: 'POST', body: values }));
    elements.registerForm.reset();
  } catch (error) {
    setMessage(elements.authMessage, error.message, true);
  }
});

elements.profileForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = formValues(elements.profileForm);
  values.discoverable = elements.profileForm.elements.discoverable.checked;
  try {
    const result = await request('/api/me', { method: 'PATCH', body: values });
    state.user = result.user;
    showDashboard();
    setMessage(elements.profileMessage, 'Profile saved.');
  } catch (error) {
    setMessage(elements.profileMessage, error.message, true);
  }
});

elements.enrollmentForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const imageFile = elements.enrollmentForm.elements.image.files[0];
  if (!imageFile) return;
  setMessage(elements.enrollmentMessage, 'Processing enrollment locally; the first run downloads the face models.');
  try {
    const image = await imageFileAsDataUrl(imageFile);
    const result = await request('/api/face-template', {
      method: 'POST',
      body: { image, consent: elements.enrollmentForm.elements.consent.checked }
    });
    state.user = result.user;
    showDashboard();
    elements.enrollmentForm.reset();
    setMessage(elements.enrollmentMessage, 'Face recognition enabled. Your photo was processed and discarded; only the template is retained.');
  } catch (error) {
    setMessage(elements.enrollmentMessage, error.message, true);
  }
});

elements.removeFaceEnrollment.addEventListener('click', async () => {
  if (!window.confirm('Delete your face template and stop allowing face searches?')) return;
  try {
    const result = await request('/api/face-template', { method: 'DELETE' });
    state.user = result.user;
    showDashboard();
    setMessage(elements.enrollmentMessage, 'Face template deleted; face search consent withdrawn.');
  } catch (error) {
    setMessage(elements.enrollmentMessage, error.message, true);
  }
});

elements.startCamera.addEventListener('click', async () => {
  if (state.cameraStream) {
    stopCamera();
    return;
  }
  try {
    state.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: 'user' },
      audio: false
    });
    elements.scanCamera.srcObject = state.cameraStream;
    elements.scanCamera.hidden = false;
    elements.cameraPlaceholder.hidden = true;
    elements.captureMatch.disabled = false;
    elements.startCamera.textContent = 'Stop camera';
    await elements.scanCamera.play();
  } catch (error) {
    setMessage(elements.scanMessage, `Could not start camera: ${error.message}`, true);
  }
});

function stopCamera() {
  if (state.cameraStream) {
    state.cameraStream.getTracks().forEach((track) => track.stop());
    state.cameraStream = null;
  }
  elements.scanCamera.srcObject = null;
  elements.scanCamera.hidden = true;
  elements.cameraPlaceholder.hidden = false;
  elements.captureMatch.disabled = true;
  elements.startCamera.textContent = 'Start camera';
}

elements.captureMatch.addEventListener('click', async () => {
  if (!elements.scanCamera.videoWidth) {
    setMessage(elements.scanMessage, 'Wait for the camera image or choose a photo.', true);
    return;
  }
  const canvas = document.createElement('canvas');
  const scale = Math.min(1, 1280 / elements.scanCamera.videoWidth);
  canvas.width = Math.round(elements.scanCamera.videoWidth * scale);
  canvas.height = Math.round(elements.scanCamera.videoHeight * scale);
  canvas.getContext('2d').drawImage(elements.scanCamera, 0, 0, canvas.width, canvas.height);
  await runFaceMatch(canvas.toDataURL('image/jpeg', 0.84));
});

elements.matchImage.addEventListener('change', async () => {
  const imageFile = elements.matchImage.files[0];
  if (!imageFile) return;
  try {
    await runFaceMatch(await imageFileAsDataUrl(imageFile));
  } catch (error) {
    setMessage(elements.scanMessage, error.message, true);
  } finally {
    elements.matchImage.value = '';
  }
});

async function imageFileAsDataUrl(file) {
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    throw new Error('Choose a JPEG, PNG, or WEBP photo.');
  }
  if (file.size > 12_000_000) throw new Error('Choose a photo smaller than 12 MB.');
  const dataUrl = await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read the selected photo.'));
    reader.readAsDataURL(file);
  });
  const image = await new Promise((resolve, reject) => {
    const loadedImage = new Image();
    loadedImage.onload = () => resolve(loadedImage);
    loadedImage.onerror = () => reject(new Error('The selected file is not a readable image.'));
    loadedImage.src = dataUrl;
  });
  const scale = Math.min(1, 1280 / image.width, 1280 / image.height);
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(image.width * scale);
  canvas.height = Math.round(image.height * scale);
  canvas.getContext('2d').drawImage(image, 0, 0, canvas.width, canvas.height);
  return canvas.toDataURL('image/jpeg', 0.84);
}

async function runFaceMatch(image) {
  setMessage(elements.scanMessage, 'Comparing against opted-in members using the local face models…');
  elements.matchResult.replaceChildren();
  elements.viewedProfile.hidden = true;
  try {
    const result = await request('/api/face-match', {
      method: 'POST',
      body: { image }
    });
    renderFaceMatch(result.match);
  } catch (error) {
    setMessage(elements.scanMessage, error.message, true);
  }
}

function renderFaceMatch(match) {
  elements.matchResult.replaceChildren();
  if (!match) {
    setMessage(elements.scanMessage, 'No opted-in enrolled profile matched this face.');
    return;
  }
  setMessage(elements.scanMessage, '');
  const card = document.createElement('div');
  card.className = 'matched-person';
  const heading = document.createElement('strong');
  heading.textContent = `Possible match: ${match.full_name}`;
  const detail = document.createElement('span');
  detail.textContent = match.is_self
    ? 'This looks like your own enrolled profile.'
    : `Similarity ${Math.round(match.similarity * 100)}% · Full profile is protected until a follow invitation is accepted.`;
  card.append(heading, detail);

  if (!match.is_self && match.follow_status === 'none') {
    card.append(createControl('Send follow invitation', 'Send follow invitation', async () => {
      try {
        await request('/api/follow-requests', {
          method: 'POST',
          body: { target_id: match.id }
        });
        setMessage(elements.scanMessage, 'Follow invitation sent. You will see their full profile after they accept.');
        await refreshFollowRequests();
      } catch (error) {
        setMessage(elements.scanMessage, error.message, true);
      }
    }));
  } else if (!match.is_self && match.follow_status === 'pending') {
    detail.textContent = 'A follow invitation is already pending between you. Check your invitations.';
  } else if (!match.is_self && match.follow_status === 'rejected') {
    card.append(createControl('Send another follow invitation', 'Request to follow', async () => {
      try {
        await request('/api/follow-requests', {
          method: 'POST',
          body: { target_id: match.id }
        });
        setMessage(elements.scanMessage, 'Follow invitation sent.');
        await refreshFollowRequests();
      } catch (error) {
        setMessage(elements.scanMessage, error.message, true);
      }
    }));
  } else if (!match.is_self && match.follow_status === 'accepted') {
    card.append(createControl('View matched profile', 'View profile', () => viewProfile(match.id)));
  }
  elements.matchResult.append(card);
}

document.getElementById('refresh-follows').addEventListener('click', refreshFollowRequests);

async function refreshFollowRequests() {
  try {
    renderFollowRequests(await request('/api/follow-requests'));
    setMessage(elements.followMessage, '');
  } catch (error) {
    setMessage(elements.followMessage, error.message, true);
  }
}

function renderFollowRequests(data) {
  elements.followRequests.replaceChildren();
  const incomingHeading = document.createElement('h3');
  incomingHeading.textContent = 'Invitations for you';
  elements.followRequests.append(incomingHeading);
  if (!data.incoming.length) {
    appendFollowNote('No pending invitations.');
  } else {
    data.incoming.forEach((follow) => {
      const row = createFollowRow(follow.person_id, follow.full_name, 'Wants to follow you');
      row.append(
        createControl('Accept follow invitation', 'Accept', () => respondToFollow(follow.id, 'accept')),
        createControl('Reject follow invitation', 'Reject', () => respondToFollow(follow.id, 'reject'))
      );
      elements.followRequests.append(row);
    });
  }
  const outgoingHeading = document.createElement('h3');
  outgoingHeading.textContent = 'Invitations you sent';
  elements.followRequests.append(outgoingHeading);
  if (!data.outgoing.length) {
    appendFollowNote('You have not sent any invitations.');
  } else {
    data.outgoing.forEach((follow) => {
      const row = createFollowRow(follow.person_id, follow.full_name, 'Waiting for their response');
      elements.followRequests.append(row);
    });
  }
  const connectionsHeading = document.createElement('h3');
  connectionsHeading.textContent = 'Mutual follows';
  elements.followRequests.append(connectionsHeading);
  if (!data.connections.length) {
    appendFollowNote('No mutual follows yet.');
  } else {
    data.connections.forEach((connection) => {
      const row = createFollowRow(connection.person_id, connection.full_name, 'Mutual follow · profile unlocked');
      row.append(createControl('View profile', 'View profile', () => viewProfile(connection.person_id)));
      elements.followRequests.append(row);
    });
  }
}

function createFollowRow(personId, nameText, detailText) {
  const row = document.createElement('div');
  row.className = 'follow-row';
  const details = document.createElement('div');
  details.className = 'follow-row-details';
  const name = document.createElement('strong');
  name.textContent = nameText;
  const detail = document.createElement('span');
  detail.textContent = detailText;
  details.append(name, detail);
  row.dataset.personId = personId;
  row.append(details);
  return row;
}

function appendFollowNote(text) {
  const note = document.createElement('p');
  note.className = 'muted follow-note';
  note.textContent = text;
  elements.followRequests.append(note);
}

async function respondToFollow(requestId, action) {
  try {
    await request(`/api/follow-requests/${encodeURIComponent(requestId)}/${action}`, {
      method: 'POST',
      body: {}
    });
    await refreshFollowRequests();
    setMessage(elements.followMessage, action === 'accept'
      ? 'Invitation accepted. You now follow each other and can view each other’s profiles.'
      : 'Invitation rejected.');
  } catch (error) {
    setMessage(elements.followMessage, error.message, true);
  }
}

async function viewProfile(profileId) {
  try {
    const result = await request(`/api/profiles/${encodeURIComponent(profileId)}`);
    renderViewedProfile(result);
  } catch (error) {
    setMessage(elements.followMessage, error.message, true);
  }
}

function renderViewedProfile(data) {
  const profile = data.profile;
  elements.viewedProfileDetails.replaceChildren();
  const details = document.createElement('div');
  details.className = 'view-profile-details';
  const email = document.createElement('p');
  email.textContent = `Email: ${profile.email}`;
  const phone = document.createElement('p');
  phone.textContent = `Phone: ${profile.phone || 'Not provided'}`;
  details.append(email, phone);

  const relatedHeading = document.createElement('h3');
  relatedHeading.textContent = `Related people (${data.related_people.length})`;
  details.append(relatedHeading);
  if (!data.related_people.length) {
    const empty = document.createElement('p');
    empty.className = 'muted';
    empty.textContent = 'No discoverable related people are listed.';
    details.append(empty);
  } else {
    const list = document.createElement('ul');
    list.className = 'related-people';
    data.related_people.forEach((relative) => {
      const item = document.createElement('li');
      const name = document.createElement('strong');
      name.textContent = relative.full_name;
      const relation = document.createElement('span');
      relation.textContent = relative.relationship;
      item.append(name, relation);
      list.append(item);
    });
    details.append(list);
  }
  elements.viewedProfileDetails.append(details);
  document.getElementById('viewed-profile-heading').textContent = profile.full_name;
  elements.viewedProfile.hidden = false;
  elements.viewedProfile.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

elements.peopleSearch.addEventListener('input', () => {
  clearTimeout(state.searchTimer);
  const query = elements.peopleSearch.value.trim();
  const sequence = ++state.searchSequence;
  elements.searchResults.replaceChildren();
  elements.contactForm.hidden = true;
  if (query.length < 2) return;
  state.searchTimer = setTimeout(() => searchPeople(query, sequence), 250);
});

async function searchPeople(query, sequence) {
  try {
    const result = await request(`/api/people?q=${encodeURIComponent(query)}`);
    if (sequence !== state.searchSequence) return;
    renderSearchResults(result.people);
  } catch (error) {
    if (sequence === state.searchSequence) {
      setMessage(elements.familyMessage, error.message, true);
    }
  }
}

function renderSearchResults(people) {
  elements.searchResults.replaceChildren();
  if (!people.length) {
    const empty = document.createElement('p');
    empty.className = 'muted search-empty';
    empty.textContent = 'No discoverable profiles found. Ask your family member to register and enable profile discovery.';
    elements.searchResults.append(empty);
    return;
  }
  people.forEach((person) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'person-result';
    const name = document.createElement('strong');
    name.textContent = person.full_name;
    const email = document.createElement('span');
    email.textContent = person.email;
    button.append(name, email);
    button.addEventListener('click', () => selectPerson(person));
    elements.searchResults.append(button);
  });
}

function selectPerson(person) {
  elements.contactForm.elements.person_id.value = person.id;
  elements.selectedPerson.textContent = `Adding ${person.full_name} (${person.email})`;
  elements.contactForm.hidden = false;
  elements.contactForm.elements.relationship.focus();
}

elements.contactForm.addEventListener('submit', async (event) => {
  event.preventDefault();
  const values = formValues(elements.contactForm);
  try {
    await request('/api/contacts', { method: 'POST', body: values });
    elements.contactForm.reset();
    elements.contactForm.hidden = true;
    elements.peopleSearch.value = '';
    elements.searchResults.replaceChildren();
    setMessage(elements.familyMessage, 'Family member added to your emergency list.');
    await refreshContacts();
  } catch (error) {
    setMessage(elements.familyMessage, error.message, true);
  }
});

async function refreshContacts() {
  const result = await request('/api/contacts');
  state.contacts = result.contacts;
  renderContacts();
}

function renderContacts() {
  elements.contactsList.replaceChildren();
  elements.contactsEmpty.hidden = state.contacts.length > 0;
  state.contacts.forEach((contact, index) => {
    const item = document.createElement('li');
    item.className = 'contact-card';

    const priority = document.createElement('span');
    priority.className = 'priority-number';
    priority.textContent = String(index + 1);

    const details = document.createElement('div');
    details.className = 'contact-details';
    const name = document.createElement('strong');
    name.textContent = contact.full_name;
    const relationship = document.createElement('span');
    relationship.textContent = contact.relationship;
    const phone = document.createElement('a');
    phone.className = 'contact-phone';
    if (contact.phone) {
      phone.href = `tel:${contact.phone}`;
      phone.textContent = contact.phone;
    } else {
      phone.textContent = 'No phone number added';
    }
    details.append(name, relationship, phone);

    const controls = document.createElement('div');
    controls.className = 'contact-controls';
    const up = createControl('Move up', '↑', () => moveContact(index, -1));
    const down = createControl('Move down', '↓', () => moveContact(index, 1));
    up.disabled = index === 0;
    down.disabled = index === state.contacts.length - 1;
    const remove = createControl('Remove contact', 'Remove', () => removeContact(contact));
    remove.classList.add('remove-button');
    controls.append(up, down, remove);
    item.append(priority, details, controls);
    elements.contactsList.append(item);
  });
}

function createControl(label, text, onClick) {
  const button = document.createElement('button');
  button.type = 'button';
  button.className = 'icon-control';
  button.setAttribute('aria-label', label);
  button.title = label;
  button.textContent = text;
  button.addEventListener('click', onClick);
  return button;
}

async function moveContact(index, offset) {
  const reordered = [...state.contacts];
  const destination = index + offset;
  [reordered[index], reordered[destination]] = [reordered[destination], reordered[index]];
  try {
    const result = await request('/api/contacts/order', {
      method: 'PUT',
      body: { contact_ids: reordered.map((contact) => contact.id) }
    });
    state.contacts = result.contacts;
    renderContacts();
    setMessage(elements.contactsMessage, 'Emergency contact order updated.');
  } catch (error) {
    setMessage(elements.contactsMessage, error.message, true);
  }
}

async function removeContact(contact) {
  if (!window.confirm(`Remove ${contact.full_name} from your emergency contacts?`)) return;
  try {
    await request(`/api/contacts/${encodeURIComponent(contact.id)}`, { method: 'DELETE' });
    await refreshContacts();
    setMessage(elements.contactsMessage, 'Emergency contact removed.');
  } catch (error) {
    setMessage(elements.contactsMessage, error.message, true);
  }
}

document.getElementById('sign-out-button').addEventListener('click', async () => {
  stopCamera();
  try {
    await request('/api/logout', { method: 'POST', body: {} });
  } catch (error) {
    setMessage(elements.authMessage, error.message, true);
  } finally {
    clearSession();
    showAuth();
  }
});

if (state.token) {
  request('/api/me')
    .then(({ user }) => {
      state.user = user;
      showDashboard();
      return loadDashboard();
    })
    .catch(() => {
      clearSession();
      showAuth();
    });
} else {
  showAuth();
}
