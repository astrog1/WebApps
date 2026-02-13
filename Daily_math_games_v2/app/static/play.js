(() => {
    const config = window.APP_CONFIG || {};
    const levelPanels = {
        level1: null,
        level2: null,
        level3: null,
    };

    const level1 = {
        active: false,
        timerId: null,
        timeLeft: 60,
        score: 0,
        queue: [],
        queueIndex: 0,
        current: null,
        locked: false,
    };

    let payload = null;

    const el = {};

    document.addEventListener("DOMContentLoaded", init);

    function init() {
        cacheElements();
        bindBaseEvents();
        updateViewportHeight();
        window.addEventListener("resize", updateViewportHeight);
        void loadTodayData();
    }

    function cacheElements() {
        el.loadingState = document.getElementById("loadingState");
        el.noDataState = document.getElementById("noDataState");
        el.gameState = document.getElementById("gameState");
        el.generateFromPlayBtn = document.getElementById("generateFromPlayBtn");
        el.generateFromPlayStatus = document.getElementById("generateFromPlayStatus");

        el.tabButtons = Array.from(document.querySelectorAll(".tab-btn"));
        levelPanels.level1 = document.getElementById("level1Panel");
        levelPanels.level2 = document.getElementById("level2Panel");
        levelPanels.level3 = document.getElementById("level3Panel");

        el.level2List = document.getElementById("level2List");
        el.level3List = document.getElementById("level3List");

        el.lvl1StartCard = document.getElementById("lvl1StartCard");
        el.lvl1GameCard = document.getElementById("lvl1GameCard");
        el.lvl1EndCard = document.getElementById("lvl1EndCard");

        el.level1StartBtn = document.getElementById("level1StartBtn");
        el.level1SubmitBtn = document.getElementById("level1SubmitBtn");
        el.level1PlayAgainBtn = document.getElementById("level1PlayAgainBtn");

        el.level1Time = document.getElementById("level1Time");
        el.level1Score = document.getElementById("level1Score");
        el.level1Question = document.getElementById("level1Question");
        el.level1Feedback = document.getElementById("level1Feedback");
        el.level1Answer = document.getElementById("level1Answer");
        el.level1FinalScore = document.getElementById("level1FinalScore");
    }

    function bindBaseEvents() {
        if (el.generateFromPlayBtn) {
            el.generateFromPlayBtn.addEventListener("click", () => {
                void generateAndReload(el.generateFromPlayBtn, el.generateFromPlayStatus);
            });
        }

        for (const button of el.tabButtons) {
            button.addEventListener("click", () => activateTab(button.dataset.level || "level1"));
        }

        if (el.level1StartBtn) {
            el.level1StartBtn.addEventListener("click", startLevel1Round);
        }

        if (el.level1SubmitBtn) {
            el.level1SubmitBtn.addEventListener("click", submitLevel1Answer);
        }

        if (el.level1PlayAgainBtn) {
            el.level1PlayAgainBtn.addEventListener("click", startLevel1Round);
        }

        if (el.level1Answer) {
            el.level1Answer.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    submitLevel1Answer();
                }
            });
        }
    }

    function updateViewportHeight() {
        document.documentElement.style.setProperty("--app-height", `${window.innerHeight}px`);
    }

    async function loadTodayData() {
        showState("loading");

        try {
            const res = await fetch(config.todayUrl || "/daily/today");

            if (res.status === 404) {
                showState("empty");
                return;
            }

            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || "Failed to load today's game");
            }

            payload = await res.json();
            showState("game");
            activateTab("level1");
            renderLevel2();
            renderLevel3();
            resetLevel1Ui();
        } catch (err) {
            showState("empty");
            if (el.generateFromPlayStatus) {
                el.generateFromPlayStatus.textContent = String(err.message || err);
            }
        }
    }

    async function generateAndReload(button, statusElement) {
        button.disabled = true;
        button.textContent = "Generating...";
        if (statusElement) {
            statusElement.textContent = "Generating with OpenAI...";
        }

        try {
            const res = await fetch(config.generateUrl || "/generate", { method: "POST" });
            if (!res.ok) {
                const data = await res.json().catch(() => ({}));
                throw new Error(data.detail || "Failed to generate game");
            }
            window.location.reload();
        } catch (err) {
            button.disabled = false;
            button.textContent = "Generate";
            if (statusElement) {
                statusElement.textContent = String(err.message || err);
            }
        }
    }

    function showState(kind) {
        const isLoading = kind === "loading";
        const isEmpty = kind === "empty";
        const isGame = kind === "game";

        if (el.loadingState) el.loadingState.hidden = !isLoading;
        if (el.noDataState) el.noDataState.hidden = !isEmpty;
        if (el.gameState) el.gameState.hidden = !isGame;
    }

    function activateTab(level) {
        for (const button of el.tabButtons) {
            const isActive = button.dataset.level === level;
            button.classList.toggle("active", isActive);
        }

        for (const [name, panel] of Object.entries(levelPanels)) {
            if (!panel) continue;
            panel.hidden = name !== level;
        }
    }

    function renderLevel2() {
        renderQaList(el.level2List, payload?.level2 || []);
    }

    function renderLevel3() {
        renderQaList(el.level3List, payload?.level3 || []);
    }

    function renderQaList(container, items) {
        if (!container) return;
        container.innerHTML = "";

        items.forEach((item, index) => {
            const card = document.createElement("article");
            card.className = "qa-item";

            const question = document.createElement("p");
            question.className = "q";
            question.textContent = `${index + 1}. ${item.question}`;

            const answerRow = document.createElement("div");
            answerRow.className = "qa-answer-row";

            const input = document.createElement("input");
            input.className = "qa-input";
            input.type = "text";
            input.autocomplete = "off";
            input.enterKeyHint = "done";
            input.placeholder = "Your answer";

            const submitButton = document.createElement("button");
            submitButton.className = "btn btn-primary qa-submit-btn";
            submitButton.type = "button";
            submitButton.textContent = "Submit";

            const feedback = document.createElement("p");
            feedback.className = "qa-feedback";
            feedback.setAttribute("aria-live", "polite");

            const expected = String(item.answer);
            const checkAnswer = () => {
                const userAnswer = input.value.trim();
                if (!userAnswer) {
                    return;
                }

                const correct = isAnswerCorrect(userAnswer, expected);
                feedback.classList.remove("correct", "incorrect");

                if (correct) {
                    feedback.textContent = "Correct";
                    feedback.classList.add("correct");
                    card.classList.add("solved");
                    input.disabled = true;
                    submitButton.disabled = true;
                } else {
                    feedback.textContent = "Incorrect";
                    feedback.classList.add("incorrect");
                }
            };

            submitButton.addEventListener("click", checkAnswer);
            input.addEventListener("keydown", (event) => {
                if (event.key === "Enter") {
                    event.preventDefault();
                    checkAnswer();
                }
            });

            answerRow.append(input, submitButton);

            const details = document.createElement("details");
            const summary = document.createElement("summary");
            summary.textContent = "Reveal answer";

            const answer = document.createElement("p");
            answer.className = "answer";
            answer.textContent = item.answer;

            details.append(summary, answer);
            card.append(question, answerRow, feedback, details);
            container.append(card);
        });
    }

    function resetLevel1Ui() {
        clearLevel1Timer();
        level1.active = false;
        level1.locked = false;
        level1.timeLeft = 60;
        level1.score = 0;
        level1.queue = [];
        level1.queueIndex = 0;
        level1.current = null;

        updateLevel1Stats();

        if (el.level1Feedback) {
            el.level1Feedback.textContent = "";
            el.level1Feedback.classList.remove("correct", "incorrect");
        }

        if (el.level1Answer) {
            el.level1Answer.value = "";
            el.level1Answer.disabled = false;
        }
        if (el.level1SubmitBtn) {
            el.level1SubmitBtn.disabled = false;
        }

        if (el.lvl1StartCard) el.lvl1StartCard.hidden = false;
        if (el.lvl1GameCard) el.lvl1GameCard.hidden = true;
        if (el.lvl1EndCard) el.lvl1EndCard.hidden = true;
    }

    function startLevel1Round() {
        const level1Questions = Array.isArray(payload?.level1) ? payload.level1 : [];
        if (level1Questions.length === 0) {
            return;
        }

        clearLevel1Timer();
        level1.active = true;
        level1.locked = false;
        level1.timeLeft = 60;
        level1.score = 0;
        level1.queue = shuffled(level1Questions.slice());
        level1.queueIndex = 0;
        level1.current = null;

        if (el.lvl1StartCard) el.lvl1StartCard.hidden = true;
        if (el.lvl1GameCard) el.lvl1GameCard.hidden = false;
        if (el.lvl1EndCard) el.lvl1EndCard.hidden = true;

        updateLevel1Stats();
        advanceLevel1Question();

        level1.timerId = window.setInterval(() => {
            level1.timeLeft -= 1;
            if (level1.timeLeft <= 0) {
                level1.timeLeft = 0;
                updateLevel1Stats();
                endLevel1Round();
                return;
            }
            updateLevel1Stats();
        }, 1000);
    }

    function submitLevel1Answer() {
        if (!level1.active || level1.locked || !level1.current) {
            return;
        }

        const rawValue = el.level1Answer ? el.level1Answer.value : "";
        const userAnswer = (rawValue || "").trim();
        if (!userAnswer) {
            return;
        }

        const expected = String(level1.current.answer);
        const correct = isAnswerCorrect(userAnswer, expected);

        level1.locked = true;
        if (el.level1Answer) el.level1Answer.disabled = true;
        if (el.level1SubmitBtn) el.level1SubmitBtn.disabled = true;

        if (correct) {
            level1.score += 1;
        }
        updateLevel1Stats();
        showFeedback(correct, expected);

        window.setTimeout(() => {
            if (!level1.active) {
                return;
            }
            level1.locked = false;
            if (el.level1Answer) el.level1Answer.disabled = false;
            if (el.level1SubmitBtn) el.level1SubmitBtn.disabled = false;
            advanceLevel1Question();
        }, 550);
    }

    function advanceLevel1Question() {
        if (!level1.active) {
            return;
        }

        if (level1.queueIndex >= level1.queue.length) {
            level1.queue = shuffled(level1.queue.slice());
            level1.queueIndex = 0;
        }

        level1.current = level1.queue[level1.queueIndex];
        level1.queueIndex += 1;

        if (el.level1Question) {
            el.level1Question.textContent = level1.current.question;
        }

        if (el.level1Feedback) {
            el.level1Feedback.textContent = "";
            el.level1Feedback.classList.remove("correct", "incorrect");
        }

        if (el.level1Answer) {
            el.level1Answer.value = "";
            el.level1Answer.focus();
        }
    }

    function endLevel1Round() {
        clearLevel1Timer();
        level1.active = false;
        level1.locked = true;

        if (el.level1Answer) {
            el.level1Answer.disabled = true;
        }
        if (el.level1SubmitBtn) {
            el.level1SubmitBtn.disabled = true;
        }

        if (el.lvl1GameCard) el.lvl1GameCard.hidden = true;
        if (el.lvl1EndCard) el.lvl1EndCard.hidden = false;
        if (el.level1FinalScore) el.level1FinalScore.textContent = String(level1.score);
    }

    function clearLevel1Timer() {
        if (level1.timerId !== null) {
            window.clearInterval(level1.timerId);
            level1.timerId = null;
        }
    }

    function updateLevel1Stats() {
        if (el.level1Time) {
            el.level1Time.textContent = `${level1.timeLeft}s`;
        }
        if (el.level1Score) {
            el.level1Score.textContent = String(level1.score);
        }
    }

    function showFeedback(correct, expected) {
        if (!el.level1Feedback) {
            return;
        }

        el.level1Feedback.classList.remove("correct", "incorrect");
        if (correct) {
            el.level1Feedback.textContent = "Correct";
            el.level1Feedback.classList.add("correct");
        } else {
            el.level1Feedback.textContent = `Incorrect. Answer: ${expected}`;
            el.level1Feedback.classList.add("incorrect");
        }
    }

    function isAnswerCorrect(userAnswer, expectedAnswer) {
        const userNum = toNumber(userAnswer);
        const expectedNum = toNumber(expectedAnswer);

        if (userNum !== null && expectedNum !== null) {
            return Math.abs(userNum - expectedNum) < 1e-9;
        }

        return normalizeText(userAnswer) === normalizeText(expectedAnswer);
    }

    function toNumber(value) {
        const normalized = String(value).replace(/,/g, "").trim();
        if (!normalized) {
            return null;
        }
        const num = Number(normalized);
        return Number.isFinite(num) ? num : null;
    }

    function normalizeText(value) {
        return String(value).trim().toLowerCase();
    }

    function shuffled(items) {
        const list = items.slice();
        for (let i = list.length - 1; i > 0; i -= 1) {
            const j = Math.floor(Math.random() * (i + 1));
            [list[i], list[j]] = [list[j], list[i]];
        }
        return list;
    }
})();
