--------------------------------------------------
🎯 CORE TECH STACK
--------------------------------------------------
- Backend: Django (Server-Side Rendered, NOT DRF)
- Frontend: HTMX (for SPA-like experience with proper URL updates)
- Styling: TailwindCSS ONLY (no Bootstrap or other CSS frameworks)
- Database: MySQL
- Queue System: Django-compatible async task queue (Celery preferred with Redis)
- Email System:
  - Must support environment-based driver:
    - MAIL_DRIVER=log → log emails to file
    - MAIL_DRIVER=smtp → send real emails via SMTP
- Progress Indicator:
  - Top progress bar for all HTMX requests (like bprogress or better UX)

--------------------------------------------------
🏗️ ARCHITECTURE & CODING STANDARDS
--------------------------------------------------
- Use Function-Based Views (FBV) ONLY
- Follow clean, domain-driven folder structure (NOT default Django clutter)
- Separate concerns properly:
  - services/
  - domains/
  - repositories (if needed)
- Use `.env` and `.env.example`
  - Include clear comments for each variable
  - Make configuration self-explanatory
- Write clean, modular, maintainable code
- Use reusable templates and partials for HTMX
- Ensure proper error handling and validation

--------------------------------------------------
🔐 SECURITY REQUIREMENTS (MANDATORY)
--------------------------------------------------
- CSRF protection
- XSS protection
- Rate limiting (login, register, password reset, etc.)
- Secure password hashing (default Django)
- Email verification REQUIRED before login
- 2FA (Time-based OTP preferred, e.g., Google Authenticator)
- Session security best practices

--------------------------------------------------
⚙️ AUTHENTICATION FEATURES
--------------------------------------------------
- Email Verification (block login until verified)
- Forgot Password (email-based reset)
- Reset Password
- Change Password (force logout after change)
- 2FA Enable/Disable
- Deactivate Account

--------------------------------------------------
📄 PUBLIC (UNAUTHENTICATED) PAGES
--------------------------------------------------
1. Landing Page
2. Login Page
   - Email
   - Password
   - Remember Me
3. Register Page
   - First Name
   - Last Name
   - Email
   - Password
   - Confirm Password
4. Forgot Password Page (email input)
5. Reset Password Page
6. About Us
7. Contact Us

--------------------------------------------------
🔐 AUTHENTICATED PAGES
--------------------------------------------------
1. Dashboard
2. Account Section:
   - Profile
   - Change Password
   - 2FA Settings
   - Deactivate Account
3. Logout

--------------------------------------------------
🎨 UI / LAYOUT REQUIREMENTS
--------------------------------------------------

📌 Guest Layout:
- Top Navbar
- Menu should dynamically change:
  IF user NOT logged in:
    - Home
    - Login
    - Register
    - About
    - Contact
  IF user logged in:
    - Home
    - Dashboard
    - About
    - Contact

📌 Authenticated Layout:
- Full-width layout
- Left sidebar navigation:
  - Collapsible (hamburger menu for mobile)
- Persistent account box:
  - Show user name
  - Profile link
  - Logout button
  - MUST be pinned to bottom regardless of content height

--------------------------------------------------
⚡ HTMX BEHAVIOR REQUIREMENTS
--------------------------------------------------
- All navigation should feel like SPA
- URLs MUST update properly (no broken browser history)
- Use partial rendering for components
- Show top progress bar on every request
- Handle errors gracefully (display messages without full reload)

--------------------------------------------------
📬 QUEUE / ASYNC TASKS
--------------------------------------------------
- Use Celery + Redis (or Django Q as fallback)
- Offload:
  - Email sending
  - Any heavy background tasks

--------------------------------------------------
📦 EXPECTED OUTPUT FROM YOU
--------------------------------------------------
1. Project folder structure (clean and scalable)
2. Key Django settings (database, email, queue)
3. Example `.env` and `.env.example`
4. Core models (User, 2FA, etc.)
5. Middleware (if needed)
6. Sample FBVs (auth flow)
7. HTMX integration examples
8. Tailwind setup
9. Queue setup (Celery config)
10. Security implementation details
11. Step-by-step setup instructions

--------------------------------------------------
❗ IMPORTANT RULES
--------------------------------------------------
- Do NOT use class-based views
- Do NOT use Django REST Framework
- Keep everything SSR + HTMX
- Code should be production-ready, not tutorial-level
- Prefer simplicity over unnecessary abstraction