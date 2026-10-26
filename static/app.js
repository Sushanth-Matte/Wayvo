/* Wayvo full-stack UI: real accounts, rides and bookings via the Flask API. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const state = {
    view: 'home', user: null, authMode: 'login', activityTab: 'requests',
    nextView: null, rides: [], activity: { requests: [], offered: [] },
    currentSearch: { from: '', to: '', date: '', sort: 'soon' }
  };

  const localDate = d => `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
  const dateAfter = days => { const d = new Date(); d.setDate(d.getDate() + days); return localDate(d); };
  const formatDate = (date, time = '') => {
    if (!date) return 'Date to be agreed';
    const d = new Date(`${date}T${time || '12:00'}`);
    return `${d.toLocaleDateString('en-IN',{weekday:'short',day:'numeric',month:'short'})}${time ? ' · ' + d.toLocaleTimeString('en-IN',{hour:'numeric',minute:'2-digit'}) : ''}`;
  };
  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  let toastTimer;

  async function api(url, options = {}) {
    const config = { method: 'GET', credentials: 'same-origin', ...options, headers: { ...(options.headers || {}) } };
    if (config.body && typeof config.body !== 'string') {
      config.headers['Content-Type'] = 'application/json';
      config.body = JSON.stringify(config.body);
    }
    const response = await fetch(url, config);
    let payload = {};
    try { payload = await response.json(); } catch (_) { /* server may return an HTML error page */ }
    if (!response.ok) throw new Error(payload.error || payload.message || `Request failed (${response.status}).`);
    return payload;
  }

  function toast(message) {
    const box = $('#toast');
    box.textContent = message;
    box.classList.add('show');
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => box.classList.remove('show'), 3600);
  }

  function updateAuthUI() {
    const loggedIn = Boolean(state.user);
    $('#userChip').classList.toggle('hidden', !loggedIn);
    $('#logoutButton').classList.toggle('hidden', !loggedIn);
    const cta = $('.topbar-actions .button');
    cta.dataset.view = loggedIn ? 'activity' : 'auth';
    cta.innerHTML = loggedIn ? 'MY ACTIVITY <span aria-hidden="true">↗</span>' : 'GET STARTED <span aria-hidden="true">↗</span>';
    $('#userChipName').textContent = state.user?.name?.split(' ')[0] || 'Rider';
    $('#welcomeName').textContent = state.user?.name?.split(' ')[0] || 'Rider';
    $('.auth-extra .small-note').textContent = 'SECURE SESSION';
  }

  function go(view) {
    const known = ['home','auth','dashboard','find','offer','activity','safety'];
    if (!known.includes(view)) view = 'home';
    if (['dashboard','find','offer','activity'].includes(view) && !state.user) {
      state.nextView = view;
      view = 'auth';
    }
    state.view = view;
    $$('.view').forEach(el => el.classList.toggle('is-visible', el.dataset.page === view));
    $$('.nav-link').forEach(el => el.classList.toggle('is-active', el.dataset.view === view || (view === 'dashboard' && el.dataset.view === 'home')));
    $('#mobileMenu').setAttribute('aria-expanded', 'false');
    $('.main-nav').classList.remove('is-open');
    updateAuthUI();
    if (view === 'dashboard') loadDashboard();
    if (view === 'find') loadRides();
    if (view === 'activity') loadActivity();
    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  function setAuthMode(mode) {
    state.authMode = mode;
    $$('.auth-tab').forEach(tab => tab.classList.toggle('is-active', tab.dataset.authTab === mode));
    $('#nameField').classList.toggle('hidden', mode !== 'signup');
    $('#authName').required = mode === 'signup';
    $('#authPassword').autocomplete = mode === 'signup' ? 'new-password' : 'current-password';
    $('#authSubmit').innerHTML = mode === 'signup' ? 'CREATE MY ACCOUNT <span>↗</span>' : 'LOG IN TO Wayvo <span>↗</span>';
    $('#authNote').textContent = mode === 'signup'
      ? 'Your account is saved to the Wayvo MySQL database.'
      : 'Log in to see your rides, manage requests and publish a route.';
  }

  async function loadRides() {
    const params = new URLSearchParams();
    if (state.currentSearch.from.trim()) params.set('from', state.currentSearch.from.trim());
    if (state.currentSearch.to.trim()) params.set('to', state.currentSearch.to.trim());
    if (state.currentSearch.date) params.set('date', state.currentSearch.date);
    params.set('sort', state.currentSearch.sort || 'soon');
    try {
      const payload = await api(`/api/rides?${params.toString()}`);
      state.rides = payload.rides || [];
      renderRides();
    } catch (error) {
      $('#rideResults').innerHTML = '';
      $('#noResults').classList.remove('hidden');
      $('#noResults h3').textContent = 'The ride board could not load.';
      $('#noResults p').textContent = error.message;
      $('#resultCount').textContent = '0';
    }
  }

  function renderRides() {
    const found = state.rides;
    $('#noResults h3').textContent = 'No rides on that route yet.';
    $('#noResults p').textContent = 'Try another place, or check back after someone posts a ride.';
    $('#resultCount').textContent = found.length;
    $('#noResults').classList.toggle('hidden', found.length !== 0);
    $('#rideResults').classList.toggle('hidden', found.length === 0);
    $('#rideResults').innerHTML = found.map(ride => {
      const already = ride.booking_status === 'pending' || ride.booking_status === 'accepted';
      const statusText = ride.booking_status === 'accepted' ? 'BOOKED' : 'REQUEST SENT';
      const driverInitials = String(ride.driver || 'Driver').split(' ').map(w => w[0]).join('').replace('.', '').slice(0,3);
      return `<article class="ride-card">
        <div class="ride-image"><img src="${escapeHTML(ride.img)}" alt="Car for ${escapeHTML(ride.from)} to ${escapeHTML(ride.to)}"><span class="seat-badge">${Number(ride.seats)} SEAT${Number(ride.seats)===1?'':'S'} OPEN</span></div>
        <div class="ride-card-body">
          <h3 class="ride-card-route">${escapeHTML(ride.from)} <span>↗</span> ${escapeHTML(ride.to)}</h3>
          <div class="ride-date">${escapeHTML(formatDate(ride.date,ride.time).toUpperCase())}</div>
          <div class="public-car-line">CAR DETAILS SHARED AFTER ACCEPTANCE</div>
          <div class="driver-line"><span class="driver-avatar">${escapeHTML(driverInitials)}</span><div><div class="driver-name">${escapeHTML(ride.driver)}</div><div class="driver-rating">★ ${escapeHTML(ride.rating || 'New driver')}</div></div><div class="ride-price">₹${Number(ride.price).toLocaleString('en-IN')}<small>PER SEAT</small></div></div>
          <button class="button ${already?'button-outline':'button-dark'}" data-request-ride="${Number(ride.id)}" ${already?'disabled':''}>${already ? statusText : 'REQUEST A SEAT'} <span>${already?'✓':'↗'}</span></button>
          <p class="private-hint">Registration number and exact pickup point are revealed after acceptance.</p>
        </div></article>`;
    }).join('');
  }

  let pendingRide = null;

  function closeBookingModal() {
    $('#bookingModal').classList.add('hidden');
    pendingRide = null;
  }

  function openBookingModal(id) {
    if (!state.user) { state.nextView = 'find'; go('auth'); return; }
    const ride = state.rides.find(item => Number(item.id) === Number(id));
    if (!ride) { toast('This ride is no longer in the list. Refresh and try again.'); return; }
    const available = Math.max(0, Math.min(4, Number(ride.seats) || 0));
    if (!available) { toast('There are no seats left on this ride.'); return; }
    pendingRide = ride;
    $('#bookingRoute').textContent = `${ride.from} → ${ride.to}`;
    $('#bookingSeats').innerHTML = Array.from({length: available}, (_, i) => {
      const count = i + 1;
      return `<option value="${count}">${count} seat${count === 1 ? '' : 's'}</option>`;
    }).join('');
    $('#bookingPrice').textContent = `₹${Number(ride.price).toLocaleString('en-IN')} per seat · Total updates with your selection.`;
    $('#bookingModal').classList.remove('hidden');
    $('#bookingSeats').focus();
  }

  async function requestRide(id, seats) {
    if (!state.user) { state.nextView = 'find'; go('auth'); return; }
    try {
      const result = await api(`/api/rides/${Number(id)}/bookings`, { method: 'POST', body: { seats: Number(seats) } });
      toast(`Request sent for ${Number(result.seats_requested || seats)} seat(s). Track it in My Activity.`);
      closeBookingModal();
      await loadRides();
    } catch (error) { toast(error.message); }
  }

  async function loadDashboard() {
    try {
      const payload = await api('/api/rides?limit=4&sort=soon');
      const rides = payload.rides || [];
      $('#dashboardRides').innerHTML = rides.length ? rides.slice(0,3).map(ride =>
        `<div class="mini-ride"><img src="${escapeHTML(ride.img)}" alt=""><div><div class="mini-route">${escapeHTML(ride.from)} <span>→</span> ${escapeHTML(ride.to)}</div><div class="mini-meta">${escapeHTML(formatDate(ride.date,ride.time).toUpperCase())} · ${Number(ride.seats)} SEATS LEFT</div></div><div class="mini-price">₹${Number(ride.price)}</div></div>`
      ).join('') : '<div class="empty-state compact-empty"><h3>No departures posted yet.</h3><p>Be the first to publish a route or check back soon.</p><button class="text-link" data-view="offer">OFFER A RIDE ↗</button></div>';
    } catch (error) {
      $('#dashboardRides').innerHTML = `<p class="form-note">${escapeHTML(error.message)}</p>`;
    }
  }

  async function loadActivity() {
    try {
      state.activity = await api('/api/activity');
      renderActivity();
    } catch (error) {
      $('#activityList').innerHTML = `<div class="activity-empty"><h3>Activity could not load.</h3><p>${escapeHTML(error.message)}</p></div>`;
    }
  }

  function statusClass(status) {
    if (status === 'accepted') return 'accepted';
    if (status === 'declined') return 'declined';
    return 'pending';
  }
  function statusLabel(status) {
    return ({ pending: 'AWAITING DRIVER', accepted: 'ACCEPTED', declined: 'DECLINED', cancelled: 'CANCELLED' })[status] || String(status).toUpperCase();
  }

  function renderActivity() {
    const requestsTab = state.activityTab === 'requests';
    const requests = state.activity.requests || [];
    const offered = state.activity.offered || [];
    $$('.activity-tab').forEach(tab => tab.classList.toggle('is-active', tab.dataset.activityTab === state.activityTab));
    $('#requestTabCount').textContent = requests.filter(r => ['pending','accepted'].includes(r.status)).length;
    $('#offeredTabCount').textContent = offered.filter(r => r.status === 'active').length;
    if (requestsTab) {
      if (!requests.length) {
        $('#activityList').innerHTML = `<div class="activity-empty"><h3>No trips on your log yet.</h3><p>Find a ride that fits your route and request a seat.</p><button class="button button-dark" data-view="find">FIND A RIDE ↗</button></div>`;
        return;
      }
      $('#activityList').innerHTML = requests.map(req => {
        const accepted = req.status === 'accepted' && req.ride_status === 'active';
        const declined = req.status === 'declined';
        const cancelled = req.status === 'cancelled' || req.ride_status === 'cancelled';
        return `<article class="activity-card">
          <div><h3 class="activity-route">${escapeHTML(req.from)} <span>→</span> ${escapeHTML(req.to)}</h3>
            <div class="activity-meta">${escapeHTML(formatDate(req.date,req.time).toUpperCase())}<br>DRIVER: ${escapeHTML(req.driver)} · ₹${Number(req.price)} PER SEAT</div>
            <div class="activity-actions">
              ${['pending','accepted'].includes(req.status) && !cancelled ? `<button class="mini-button" data-cancel-booking="${Number(req.booking_id)}">${accepted?'CANCEL BOOKING':'CANCEL REQUEST'}</button>` : ''}
              ${declined ? `<button class="mini-button" data-retry-request="${Number(req.ride_id)}">REQUEST AGAIN</button>` : ''}
            </div>
          </div>
          <span class="status-pill ${cancelled?'pending':statusClass(req.status)}">${cancelled?'CANCELLED':statusLabel(req.status)}</span>
          ${accepted ? `<div class="confirmed-details">
            <div class="confirmed-detail"><span>DRIVER MOBILE</span><strong><a href="tel:${escapeHTML(req.driver_phone || '')}" class="phone-link">${escapeHTML(req.driver_phone || 'Not provided')}</a></strong></div>
            <div class="confirmed-detail"><span>CAR MODEL / COLOUR</span><strong>${escapeHTML(req.car)} · ${escapeHTML(req.color || 'Not specified')}</strong></div>
            <div class="confirmed-detail"><span>REGISTRATION NUMBER</span><strong>${escapeHTML(req.reg || 'Not provided')}</strong></div>
            <div class="confirmed-detail"><span>EXACT PICKUP LOCATION</span><strong>${escapeHTML(req.pickup || 'Confirm with driver')}</strong></div>
            ${req.drop ? `<div class="confirmed-detail"><span>DROP-OFF POINT</span><strong>${escapeHTML(req.drop)}</strong></div>` : ''}
          </div>` : (req.status === 'pending' ? '<p class="private-hint activity-private-hint">Car registration and exact pickup details will appear here if the driver accepts.</p>' : '')}
        </article>`;
      }).join('');
    } else {
      if (!offered.length) {
        $('#activityList').innerHTML = `<div class="activity-empty"><h3>Your passenger seats are waiting.</h3><p>Publish a route you're already taking and share the drive.</p><button class="button button-dark" data-view="offer">OFFER A RIDE ↗</button></div>`;
        return;
      }
      $('#activityList').innerHTML = offered.map(ride => {
        const rideActive = ride.status === 'active';
        const requestsHtml = (ride.bookings || []).map(booking => `<div class="passenger-request">
          <div><strong>${escapeHTML(booking.passenger_name)}</strong><span>${escapeHTML(statusLabel(booking.status))} · ${Number(booking.seats_requested)} seat</span></div>
          ${booking.status === 'pending' && rideActive ? `<div class="activity-actions"><button class="mini-button" data-accept-booking="${Number(booking.id)}">ACCEPT</button><button class="mini-button" data-decline-booking="${Number(booking.id)}">DECLINE</button></div>` : ''}
        </div>`).join('');
        return `<article class="activity-card">
          <div><h3 class="activity-route">${escapeHTML(ride.from)} <span>→</span> ${escapeHTML(ride.to)}</h3><div class="activity-meta">${escapeHTML(formatDate(ride.date,ride.time).toUpperCase())}<br>${Number(ride.seats)} OPEN SEAT${Number(ride.seats)===1?'':'S'} · ₹${Number(ride.price)} PER SEAT</div>
          <div class="activity-actions">${rideActive ? `<button class="mini-button" data-cancel-offer="${Number(ride.id)}">CANCEL RIDE</button>` : ''}</div></div>
          <span class="status-pill ${rideActive?'accepted':'pending'}">${rideActive?'PUBLISHED':'CANCELLED'}</span>
          <div class="confirmed-details"><div class="confirmed-detail"><span>CAR MODEL / COLOUR</span><strong>${escapeHTML(ride.car)} · ${escapeHTML(ride.color || 'Not specified')}</strong></div><div class="confirmed-detail"><span>REGISTRATION NUMBER</span><strong>${escapeHTML(ride.reg)}</strong></div><div class="confirmed-detail"><span>PICKUP LOCATION</span><strong>${escapeHTML(ride.pickup)}</strong></div>${ride.drop ? `<div class="confirmed-detail"><span>DROP-OFF POINT</span><strong>${escapeHTML(ride.drop)}</strong></div>` : ''}</div>
          <div class="driver-requests"><div class="driver-requests-heading">PASSENGER REQUESTS <span>${(ride.bookings || []).filter(b=>b.status==='pending').length} PENDING</span></div>${requestsHtml || '<p class="form-note">No passenger requests for this ride yet.</p>'}</div>
        </article>`;
      }).join('');
    }
  }

  async function finishLogin(user) {
    state.user = user;
    updateAuthUI();
    const destination = state.nextView || 'dashboard';
    state.nextView = null;
    toast(`Welcome to Wayvo, ${user.name.split(' ')[0]}.`);
    go(destination);
  }

  document.addEventListener('click', async event => {
    const nav = event.target.closest('[data-view]');
    if (nav) { event.preventDefault(); go(nav.dataset.view); return; }
    const authTab = event.target.closest('[data-auth-tab]');
    if (authTab) { setAuthMode(authTab.dataset.authTab); return; }
    const activityTab = event.target.closest('[data-activity-tab]');
    if (activityTab) { state.activityTab = activityTab.dataset.activityTab; renderActivity(); return; }
    const request = event.target.closest('[data-request-ride]');
    if (request) { openBookingModal(request.dataset.requestRide); return; }
    if (event.target.closest('#bookingClose, #bookingCancel')) { closeBookingModal(); return; }
    const cancelBooking = event.target.closest('[data-cancel-booking]');
    if (cancelBooking) {
      try { await api(`/api/bookings/${Number(cancelBooking.dataset.cancelBooking)}/cancel`, { method: 'POST', body: {} }); toast('Booking cancelled.'); await Promise.all([loadActivity(), loadRides()]); }
      catch (error) { toast(error.message); }
      return;
    }
    const accept = event.target.closest('[data-accept-booking]');
    if (accept) {
      try { await api(`/api/bookings/${Number(accept.dataset.acceptBooking)}/accept`, { method: 'POST', body: {} }); toast('Request accepted. The passenger can now see the car and pickup details.'); await Promise.all([loadActivity(), loadRides()]); }
      catch (error) { toast(error.message); }
      return;
    }
    const decline = event.target.closest('[data-decline-booking]');
    if (decline) {
      try { await api(`/api/bookings/${Number(decline.dataset.declineBooking)}/decline`, { method: 'POST', body: {} }); toast('Booking request declined.'); await loadActivity(); }
      catch (error) { toast(error.message); }
      return;
    }
    const retry = event.target.closest('[data-retry-request]');
    if (retry) { openBookingModal(retry.dataset.retryRequest); return; }
    const cancelOffer = event.target.closest('[data-cancel-offer]');
    if (cancelOffer) {
      if (!window.confirm('Cancel this ride? Pending and accepted bookings will also be cancelled.')) return;
      try { await api(`/api/rides/${Number(cancelOffer.dataset.cancelOffer)}/cancel`, { method: 'POST', body: {} }); toast('Ride cancelled.'); await Promise.all([loadActivity(), loadRides()]); }
      catch (error) { toast(error.message); }
      return;
    }
    if (event.target.closest('#logoutButton')) {
      try { await api('/api/auth/logout', { method: 'POST', body: {} }); state.user = null; state.activity = { requests: [], offered: [] }; updateAuthUI(); go('home'); toast('You are logged out.'); }
      catch (error) { toast(error.message); }
    }
  });

  $('#mobileMenu').addEventListener('click', () => {
    const nav = $('.main-nav');
    const open = nav.classList.toggle('is-open');
    $('#mobileMenu').setAttribute('aria-expanded', String(open));
  });

  $('#authForm').addEventListener('submit', async event => {
    event.preventDefault();
    const name = $('#authName').value.trim();
    const email = $('#authEmail').value.trim();
    const password = $('#authPassword').value;
    if (state.authMode === 'signup' && !name) { toast('Enter your name to create an account.'); return; }
    const path = state.authMode === 'signup' ? '/api/auth/signup' : '/api/auth/login';
    const body = { name, email, password, remember: $('#rememberMe').checked };
    const submit = $('#authSubmit');
    submit.disabled = true;
    try {
      const result = await api(path, { method: 'POST', body });
      await finishLogin(result.user);
      $('#authForm').reset();
    } catch (error) { toast(error.message); }
    finally { submit.disabled = false; }
  });

  $('#searchForm').addEventListener('submit', async event => {
    event.preventDefault();
    state.currentSearch = {
      from: $('#searchFrom').value,
      to: $('#searchTo').value,
      date: $('#searchDate').value,
      sort: $('#sortRides').value
    };
    await loadRides();
    const count = state.rides.length;
    toast(count ? `${count} ride${count === 1 ? '' : 's'} found.` : 'No rides match yet. Try another route or date.');
  });

  $('#sortRides').addEventListener('change', async () => {
    state.currentSearch.sort = $('#sortRides').value;
    await loadRides();
  });

  $('#bookingForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (!pendingRide) return;
    const rideId = pendingRide.id;
    const seats = Number($('#bookingSeats').value);
    const submit = $('#bookingConfirm');
    submit.disabled = true;
    try { await requestRide(rideId, seats); }
    finally { submit.disabled = false; }
  });

  $('#bookingModal').addEventListener('click', event => {
    if (event.target.id === 'bookingModal') closeBookingModal();
  });

  $('#bookingSeats').addEventListener('change', () => {
    if (!pendingRide) return;
    const total = Number(pendingRide.price) * Number($('#bookingSeats').value);
    $('#bookingPrice').textContent = `₹${Number(pendingRide.price).toLocaleString('en-IN')} per seat · ₹${total.toLocaleString('en-IN')} total`;
  });

  $('#offerForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (!state.user) { state.nextView = 'offer'; go('auth'); return; }
    const body = {
      from: $('#offerFrom').value.trim(), to: $('#offerTo').value.trim(),
      pickup: $('#offerPickup').value.trim(), drop: $('#offerDrop').value.trim(),
      date: $('#offerDate').value, time: $('#offerTime').value,
      seats: Number($('#offerSeats').value), price: $('#offerPrice').value,
      car: $('#offerCar').value.trim(), color: $('#offerColor').value.trim(),
      reg: $('#offerReg').value.trim().toUpperCase(), phone: $('#offerPhone').value.trim(), notes: $('#offerNotes').value.trim()
    };
    if (body.from.toLowerCase() === body.to.toLowerCase()) { toast('Starting point and destination must be different.'); return; }
    const submit = event.submitter;
    if (submit) submit.disabled = true;
    try {
      await api('/api/rides', { method: 'POST', body });
      event.target.reset();
      $('#offerDate').value = dateAfter(1);
      $('#offerSeats').value = '2';
      $('#offerPrice').value = '250';
      state.activityTab = 'offered';
      toast('Your ride is published to the shared ride board.');
      go('activity');
    } catch (error) { toast(error.message); }
    finally { if (submit) submit.disabled = false; }
  });

  async function boot() {
    $('#offerDate').min = dateAfter(0);
    $('#offerDate').value = dateAfter(1);
    $('#searchDate').min = dateAfter(0);
    setAuthMode('login');
    try {
      const result = await api('/api/me');
      state.user = result.user || null;
      updateAuthUI();
    } catch (error) {
      toast(`Backend connection issue: ${error.message}`);
    }
  }
  boot();
})();
