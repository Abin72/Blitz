/* ==========================================================
   GovScheme AI
   Premium AI Frontend
   script.js
========================================================== */

document.addEventListener("DOMContentLoaded", () => {

    /* ==========================
       LOADER
    ========================== */

    const loader = document.querySelector(".loader");

    window.addEventListener("load", () => {

        if (loader) {

            loader.classList.add("hidden");

            setTimeout(() => {

                loader.remove();

            }, 500);

        }

    });

    /* ==========================
       NAVBAR
    ========================== */

    const navbar = document.getElementById("navbar");

    window.addEventListener("scroll", () => {

        if (!navbar) return;

        if (window.scrollY > 80) {

            navbar.classList.add("active");

        } else {

            navbar.classList.remove("active");

        }

    });

    /* ==========================
       COUNTERS
    ========================== */

    const counters = document.querySelectorAll(".counter");

    const counterObserver = new IntersectionObserver(entries => {

        entries.forEach(entry => {

            if (!entry.isIntersecting) return;

            const counter = entry.target;

            const target = Number(counter.dataset.target);

            let value = 0;

            const step = Math.max(1, Math.ceil(target / 120));

            const timer = setInterval(() => {

                value += step;

                if (value >= target) {

                    value = target;

                    clearInterval(timer);

                }

                counter.textContent = value.toLocaleString();

            }, 15);

            counterObserver.unobserve(counter);

        });

    });

    counters.forEach(counter => counterObserver.observe(counter));

    /* ==========================
       FADE ANIMATION
    ========================== */

    const fadeItems = document.querySelectorAll(".fade");

    const fadeObserver = new IntersectionObserver(entries => {

        entries.forEach(entry => {

            if (entry.isIntersecting) {

                entry.target.classList.add("show");

            }

        });

    }, {

        threshold: .15

    });

    fadeItems.forEach(item => fadeObserver.observe(item));

    /* ==========================
       SCROLL TO TOP
    ========================== */

    const scrollBtn = document.getElementById("scrollTop");

    if (scrollBtn) {

        window.addEventListener("scroll", () => {

            if (window.scrollY > 400) {

                scrollBtn.classList.add("show");

            } else {

                scrollBtn.classList.remove("show");

            }

        });

        scrollBtn.addEventListener("click", () => {

            window.scrollTo({

                top: 0,

                behavior: "smooth"

            });

        });

    }

    /* ==========================
       TYPING EFFECT
    ========================== */

    const typing = document.querySelector(".typing");

    if (typing) {

        const words = [

            "Government Schemes",

            "AI Recommendations",

            "Citizen Benefits",

            "Smart Eligibility"

        ];

        let wordIndex = 0;

        let charIndex = 0;

        let deleting = false;

        function type() {

            const word = words[wordIndex];

            if (!deleting) {

                typing.textContent = word.substring(0, charIndex++);

                if (charIndex > word.length) {

                    deleting = true;

                    setTimeout(type, 1800);

                    return;

                }

            } else {

                typing.textContent = word.substring(0, charIndex--);

                if (charIndex < 0) {

                    deleting = false;

                    wordIndex = (wordIndex + 1) % words.length;

                    charIndex = 0;

                }

            }

            setTimeout(type, deleting ? 45 : 90);

        }

        type();

    }

    /* ==========================
       MOUSE GLOW
    ========================== */

    const glow = document.createElement("div");

    glow.className = "cursor-glow";

    document.body.appendChild(glow);

    document.addEventListener("mousemove", e => {

        glow.style.left = e.clientX + "px";

        glow.style.top = e.clientY + "px";

    });

    /* ==========================
       BUTTON RIPPLE
    ========================== */

    document.querySelectorAll(".button").forEach(button => {

        button.addEventListener("click", e => {

            const circle = document.createElement("span");

            const diameter = Math.max(button.clientWidth, button.clientHeight);

            circle.style.width = circle.style.height = diameter + "px";

            circle.style.left = e.offsetX - diameter / 2 + "px";

            circle.style.top = e.offsetY - diameter / 2 + "px";

            circle.classList.add("ripple");

            const oldRipple = button.querySelector(".ripple");

            if (oldRipple) oldRipple.remove();

            button.appendChild(circle);

        });

    });

    /* ==========================
       SMOOTH ANCHOR LINKS
    ========================== */

    document.querySelectorAll('a[href^="#"]').forEach(link => {

        link.addEventListener("click", e => {

            const target = document.querySelector(link.getAttribute("href"));

            if (!target) return;

            e.preventDefault();

            target.scrollIntoView({

                behavior: "smooth"

            });

        });

    });

});