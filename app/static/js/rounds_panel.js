function initRoundsPanel(root) {
  if (!root) return;
  const WEEKDAY_NAMES = ["일", "월", "화", "수", "목", "금", "토"];

  function toIso(d) {
    return d.getFullYear() + "-" + String(d.getMonth() + 1).padStart(2, "0") + "-" + String(d.getDate()).padStart(2, "0");
  }
  function nextMonday() {
    const d = new Date();
    const day = d.getDay();
    let diff = (1 - day + 7) % 7;
    if (diff === 0) diff = 7;
    d.setDate(d.getDate() + diff);
    return d;
  }

  function setupDateDefaults() {
    const startField = root.querySelector("#round-start");
    const endField = root.querySelector("#round-end");
    const hintEl = root.querySelector(".range-weekday-hint");
    if (!startField || !endField || !hintEl) return;

    const activeWeekdayNames = JSON.parse(hintEl.dataset.activeWeekdays || "[]");
    const today = toIso(new Date());

    if (!startField.value) {
      const defaultStart = nextMonday();
      const defaultEnd = new Date(defaultStart);
      defaultEnd.setDate(defaultStart.getDate() + 6);
      startField.value = toIso(defaultStart);
      endField.value = toIso(defaultEnd);
    }
    endField.min = today;

    function updateHint() {
      if (!startField.value || !endField.value) return;
      if (endField.value < startField.value) {
        hintEl.textContent = "⚠️ 종료일이 시작일보다 빠릅니다.";
        hintEl.style.color = "#d98080";
        return;
      }
      const start = new Date(startField.value + "T00:00:00");
      const end = new Date(endField.value + "T00:00:00");
      const names = [];
      for (let d = new Date(start); d <= end; d.setDate(d.getDate() + 1)) {
        const name = WEEKDAY_NAMES[d.getDay()];
        if (!names.includes(name)) names.push(name);
      }
      const overlap = names.some((n) => activeWeekdayNames.includes(n));
      if (activeWeekdayNames.length === 0) {
        hintEl.textContent = `선택한 기간의 요일: ${names.join(", ")}. (아직 선생님/회원의 고정 가능 시간이 겹치는 요일이 없어요)`;
        hintEl.style.color = "#dda85e";
      } else if (overlap) {
        hintEl.textContent = `선택한 기간의 요일: ${names.join(", ")}. 가능 시간이 설정된 요일(${activeWeekdayNames.join(", ")})이 포함되어 있어요.`;
        hintEl.style.color = "#6fae8b";
      } else {
        hintEl.textContent = `⚠️ 선택한 기간의 요일(${names.join(", ")})에는 아무도 가능 시간을 설정하지 않았어요. 가능 시간이 설정된 요일은 ${activeWeekdayNames.join(", ")}입니다. 기간을 늘려주세요.`;
        hintEl.style.color = "#d98080";
      }
    }
    startField.addEventListener("change", function () {
      endField.min = startField.value;
      if (endField.value < startField.value) endField.value = startField.value;
      updateHint();
    });
    endField.addEventListener("change", updateHint);
    updateHint();
  }

  function refresh(html) {
    root.innerHTML = html;
    setupDateDefaults();
  }

  root.addEventListener("submit", function (e) {
    const roundForm = e.target.closest("#round-form");
    const deleteForm = e.target.closest(".round-delete-form");
    if (roundForm) {
      e.preventDefault();
      const startField = root.querySelector("#round-start");
      const endField = root.querySelector("#round-end");
      if (endField.value < startField.value) {
        alert("종료일이 시작일보다 빠를 수 없어요.");
        return;
      }
      fetch(roundForm.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new FormData(roundForm),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.message) alert(data.message);
          if (data.html) refresh(data.html);
        });
    } else if (deleteForm) {
      e.preventDefault();
      if (!confirm("이 회차를 삭제할까요? (아직 확정되지 않은 배정은 함께 삭제됩니다)")) return;
      fetch(deleteForm.action, {
        method: "POST",
        headers: { "X-Requested-With": "fetch" },
        body: new FormData(deleteForm),
      })
        .then((r) => r.json())
        .then((data) => {
          if (data.html) refresh(data.html);
        });
    }
  });

  setupDateDefaults();
}
