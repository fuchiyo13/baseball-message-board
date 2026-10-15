(function () {
  var weekdays = ["月", "火", "水", "木", "金", "土", "日"];
  var dateInput = document.querySelector("#event_date");
  var weekday = document.querySelector("#weekday-preview");
  var timeSlot = document.querySelector("#time_slot");
  var customTime = document.querySelector("#custom-time");
  var prefecture = document.querySelector("#prefecture");
  var area = document.querySelector("#area");

  function refreshWeekday() {
    if (!weekday) {
      return;
    }
    if (!dateInput || !dateInput.value) {
      weekday.textContent = "—";
      return;
    }
    var parts = dateInput.value.split("-").map(Number);
    var date = new Date(parts[0], parts[1] - 1, parts[2]);
    if (Number.isNaN(date.getTime())) {
      weekday.textContent = "—";
      return;
    }
    weekday.textContent = weekdays[(date.getDay() + 6) % 7] + "曜日";
  }

  function refreshTime() {
    if (!timeSlot || !customTime) {
      return;
    }
    customTime.hidden = timeSlot.value !== "custom";
  }

  function refreshAreas() {
    if (!prefecture || !area) {
      return;
    }
    var selected = prefecture.value;
    var groups = area.querySelectorAll("optgroup");
    for (var i = 0; i < groups.length; i += 1) {
      groups[i].hidden = Boolean(selected) && groups[i].dataset.pref !== selected;
    }
    var current = area.selectedOptions[0];
    if (current && current.parentElement && current.parentElement.hidden) {
      area.value = "";
    }
  }

  function decodePart(value) {
    return atob(value).split("").reverse().join("");
  }

  if (dateInput) {
    dateInput.addEventListener("change", refreshWeekday);
    dateInput.addEventListener("input", refreshWeekday);
    refreshWeekday();
  }
  if (timeSlot) {
    timeSlot.addEventListener("change", refreshTime);
    refreshTime();
  }
  if (prefecture && area) {
    prefecture.addEventListener("change", refreshAreas);
    refreshAreas();
  }

  var mailButtons = document.querySelectorAll(".js-mail");
  for (var n = 0; n < mailButtons.length; n += 1) {
    mailButtons[n].addEventListener("click", function (event) {
      var button = event.currentTarget;
      var user = decodePart(button.dataset.u);
      var host = decodePart(button.dataset.h);
      var subject = button.dataset.subject || "";
      window.location.href = "mailto:" + user + "@" + host + "?subject=" + encodeURIComponent(subject);
    });
  }

  var mask = document.querySelector("#mail-mask");
  if (mask && mailButtons.length) {
    var userName = decodePart(mailButtons[0].dataset.u);
    var hostName = decodePart(mailButtons[0].dataset.h);
    mask.textContent = userName.slice(0, 1) + "***@" + hostName;
  }

  var shareButton = document.querySelector(".js-share");
  var sharePayload = document.querySelector("#share-payload");
  if (shareButton && sharePayload) {
    shareButton.addEventListener("click", function () {
      var data = JSON.parse(sharePayload.textContent);
      var note = document.querySelector("#share-note");
      function copied() {
        shareButton.textContent = "コピーしました";
        if (note) {
          note.hidden = false;
        }
      }
      if (navigator.share) {
        navigator.share({ title: data.title, text: data.text, url: data.url }).catch(function (error) {
          if (error && error.name === "AbortError") {
            return;
          }
          copyShare(data, copied);
        });
        return;
      }
      copyShare(data, copied);
    });
  }

  function copyShare(data, done) {
    var full = data.text + "\n" + data.url;
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(full).then(done).catch(function () {
        window.prompt("この文章をコピーしてください", full);
      });
      return;
    }
    window.prompt("この文章をコピーしてください", full);
  }

  var confirms = document.querySelectorAll("form[data-confirm]");
  for (var c = 0; c < confirms.length; c += 1) {
    confirms[c].addEventListener("submit", function (event) {
      if (!window.confirm(event.currentTarget.dataset.confirm)) {
        event.preventDefault();
      }
    });
  }

  var FILTER_KEY = "board-filter-v1";
  var rememberKeys = ["prefecture", "area", "post_type", "level", "weekend"];
  var filterForm = document.querySelector("[data-remember-filters]");

  function readStoredFilters() {
    try {
      return JSON.parse(window.localStorage.getItem(FILTER_KEY) || "{}") || {};
    } catch (error) {
      return {};
    }
  }

  function saveFiltersFromUrl() {
    var params = new URLSearchParams(window.location.search);
    var stored = {};
    for (var i = 0; i < rememberKeys.length; i += 1) {
      var key = rememberKeys[i];
      var value = params.get(key);
      if (value) {
        stored[key] = value;
      }
    }
    try {
      window.localStorage.setItem(FILTER_KEY, JSON.stringify(stored));
    } catch (error) {
      /* ignore quota / private mode */
    }
  }

  function shouldRestoreFilters() {
    if (window.location.pathname !== "/") {
      return false;
    }
    var params = new URLSearchParams(window.location.search);
    if (params.has("q") || params.has("on") || params.has("page") || params.has("sort") || params.has("status")) {
      return false;
    }
    for (var i = 0; i < rememberKeys.length; i += 1) {
      if (params.has(rememberKeys[i])) {
        return false;
      }
    }
    return true;
  }

  if (shouldRestoreFilters()) {
    var saved = readStoredFilters();
    var restore = new URLSearchParams();
    for (var r = 0; r < rememberKeys.length; r += 1) {
      var rk = rememberKeys[r];
      if (saved[rk]) {
        restore.set(rk, saved[rk]);
      }
    }
    if ([].slice.call(restore.keys()).length) {
      window.location.replace("/?" + restore.toString());
      return;
    }
  }

  if (window.location.pathname === "/") {
    saveFiltersFromUrl();
  }

  if (filterForm) {
    filterForm.addEventListener("submit", function () {
      var stored = {};
      var prefectureEl = filterForm.querySelector("#prefecture");
      var areaEl = filterForm.querySelector("#area");
      var levelEl = filterForm.querySelector("#level");
      var typeEl = filterForm.querySelector('input[name="post_type"]');
      var weekendEl = filterForm.querySelector('input[name="weekend"]');
      if (prefectureEl && prefectureEl.value) {
        stored.prefecture = prefectureEl.value;
      }
      if (areaEl && areaEl.value) {
        stored.area = areaEl.value;
      }
      if (levelEl && levelEl.value) {
        stored.level = levelEl.value;
      }
      if (typeEl && typeEl.value) {
        stored.post_type = typeEl.value;
      }
      if (weekendEl && weekendEl.value === "1") {
        stored.weekend = "1";
      }
      try {
        window.localStorage.setItem(FILTER_KEY, JSON.stringify(stored));
      } catch (error) {
        /* ignore */
      }
    });
  }
})();
