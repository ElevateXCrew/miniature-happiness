# AI Booking Assistant: Features and Flow

## 1) Core Purpose
The system is a conversational booking assistant that:
- talks to clients naturally
- collects booking information step by step
- remembers returning clients
- keeps track of bookings through their lifecycle
- supports admin review and confirmation
- handles receipts, reminders, cancellations, and follow-ups

It should feel like a real assistant, not a form or chatbot.

---

## 2) Main User Experiences

### A. Client Conversation
Clients can:
- start a chat by message or call
- ask about availability, rates, and services
- provide booking details gradually
- confirm or change details during the conversation
- send payment proof or receipts
- return later and continue where they left off

The assistant should keep the conversation smooth, personal, and natural.

---

### B. Booking Collection
The assistant should gather all required booking details through a normal conversation, not a rigid form.

Typical details include:
- client name (less priority)
- age
- ethnicity/background
- booking type (Incall/Outcall)
- date
- time
- duration
- location if needed
- total price
- deposit or advance payment if needed (Only for outcall)

The assistant should only ask for what is missing and avoid repeating questions unnecessarily.

---

### C. Confirmation Flow
Once all required details are collected:
- the assistant summarizes the booking
- asks the client to confirm
- waits for a clear yes
- then marks the booking as ready for admin review

The booking should not be considered final until that confirmation step is complete.

---

### D. Receipt Handling
Clients may send proof of payment or booking-related images.

The system should:
- accept receipt images
- associate them with the correct booking when possible
- keep them if the booking has not been created yet
- acknowledge them naturally
- make them visible to the admin

---

### E. Admin Review
Admins need a control panel where they can:
- review new bookings
- confirm or decline them
- mark bookings complete or cancelled
- inspect receipts
- view conversation history
- monitor active sessions
---

### F. Ongoing Memory
The assistant should remember:
- who the client is
- what booking stage they are in
- whether they already provided age/name/ethnicity
- whether a booking is active, pending, confirmed, completed, or cancelled

This memory should survive interruptions and allow the assistant to continue naturally later.

---

## 3) Booking Lifecycle

### Step 1: Conversation Starts
The client sends a message or calls.

The assistant:
- greets them
- figures out whether they are booking, asking a question, or following up
- begins a natural conversation

---

### Step 2: Booking Intent Appears
If the client seems interested in booking:
- the assistant starts collecting details gradually
- asks one thing at a time if needed
- keeps the flow conversational

---

### Step 3: Information Gathering
The assistant collects all required details:
- identity details
- booking preferences
- timing
- duration
- type of booking
- address if relevant
- pricing and payment details

If anything is missing, the assistant gently asks for it.

---

### Step 4: Summary and Client Confirmation
When everything needed is present:
- the assistant summarizes the booking clearly
- asks the client to confirm
- waits for a direct affirmative response
- confirmation handling is server-gated so review progression only happens with a persisted draft booking

---

### Step 5: Booking Saved
After availability succeeds, the system ensures a draft booking is persisted and linked to the active session.
After the client confirms:
- the booking transitions from draft to review state
- it becomes visible for admin review
- the client remains in the conversation with context preserved

---

### Step 6: Admin Action
The admin can then:
- confirm the booking
- reject it
- edit it
- mark it complete
- cancel it
- can see live chat bwtween the agent and client 

The assistant should respond accordingly.

---

### Step 7: Completion or Reset
When a booking is finished:
- booking-specific details are cleared
- personal memory can remain if needed
- the assistant is ready for the next booking from the same client

---

## 4) Conversation Principles

The assistant should:
- sound human
- feel warm and confident
- avoid repeating itself
- adapt to the client’s tone
- stay consistent in personality
- guide the conversation without sounding pushy

It should not feel like a checklist or appointment form.

---

## 5) Client Memory Rules

The assistant should remember useful context such as:
- client identity
- past conversation state
- active booking details
- whether the client already confirmed something
- whether they have an upcoming booking
- whether a receipt has already been sent

It should use memory to reduce friction and avoid asking again for things already known.

---

## 6) Availability and Conflict Handling

If the requested time is unavailable:
- the assistant should say so politely
- suggest a better time
- avoid promising something that can’t be delivered
- Keep a 15 Minutes gaps between multiple bookings

It should never pretend a booking is available if it conflicts with another one.

---

## 7) Status Handling

A booking can move through clear states such as:
- pending
- confirmed
- completed
- cancelled

Each status should affect how the assistant behaves:
- pending: waiting for admin review
- confirmed: notify client appropriately
- completed: reset the booking flow for future use
- cancelled: stop the active process politely

---

## 8) Admin Controls

The admin should be able to:
- see all bookings
- search and filter them
- inspect conversation history
- manage active client sessions
- control whether the assistant is currently active
- view incoming receipts or notifications
- handle follow-up actions quickly

---

## 9) Pause / Resume Behavior

The assistant should support being turned off temporarily.

When off:
- it should not respond normally
- it should quietly queue incoming messages
- nothing should be lost

When turned back on:
- it should process queued messages in order
- continue naturally as though nothing was missed

---

## 10) Reminder Behavior

The system should support reminders for upcoming bookings.

These reminders might:
- go to the client
- notify the admin
- be based on time before the booking
- happen automatically

The reminders should be timely and not repetitive.

---

## 11) What Makes This System Good

A strong version of this product is defined by:
- natural conversation
- smooth booking collection
- reliable memory
- clean booking lifecycle management
- admin visibility
- graceful handling of receipts and confirmations
- zero lost context when clients return later

---

## 12) High-Level Flow Summary

1. Client contacts the assistant  
2. Assistant starts conversation naturally  
3. Assistant recognizes booking intent  
4. Assistant collects missing booking details  
5. Assistant summarizes the booking  
6. Client confirms  
7. Booking is saved  
8. Admin reviews and approves  
9. Client receives confirmation  
10. Booking progresses to completed or cancelled  
11. Assistant resets for the next interaction

# Additional Points & Sum Up
## 1) The Four-Entity Model

### 1) Entities
The system operates within a multi-way interaction environment:

1.  **The Admin:** Monitors the control panel, reviews pending bookings, inspects receipts, and provides final confirmation or cancellation.
    
2.  **The Worker:** The individual on whose behalf the Agent speaks. The system manages their specific schedule, rates, and preferences.
    
3.  **The Agent (AI):** It is the primary entity, around while other three will communicate. The conversational system that talks to Clients and Workers. It is responsible for generating human-like responses and calling "Tools" to update the backend.
    
4.  **The Client:** The person inquiring about services and making bookings.
### 2) Relation of three entities with Agent
1. **Agent to Admin:** When admin confirms, rejects, or cancels a booking from the control panel, backend sends an internal status instruction to the agent runtime. Alysha then sends the client decision update in 1-2 lines, aligned with the recent conversation context. Admin can still edit booking status from the panel.
2. **Admin Live Chat Moderation:** Admin can clear a selected session's previous conversation history from the Live Chat panel when moderation or cleanup is required.
3. . **Agent to Worker:** As the agent is conversing with client on behalf of the worker, the worker can ask any query about the bookings, ask agent for changing or adjusting booking timing. The AI must aware about the worker and repose like an assistant of the worker.
4. **Agent to Client:** The agent should converse naturally with the client.
    

## 2) Deterministic Control Philosophy

To ensure 100% reliability, the "brain" of the operation is split:

-   **The Agent (LLM):** Solely responsible for **Natural Language Understanding (NLU)** and **Generation**. It extracts details (like time, duration, or age) and passes them to the backend via tool calls.
    
-   **The Backend (State Machine):** The "Source of Truth." It validates data, checks for conflicts, enforces the 15-minute gap rule, and moves bookings through their lifecycle.
-   **Deterministic Pre-Capture:** Before LLM generation, backend attempts to capture the next required booking field directly from inbound text so the assistant does not re-ask the same question after the client has already answered.
    
-   **No Hallucinations:** The Agent never "decides" a booking is confirmed. It only reports what the backend state allows it to say.
    

## 3) Long-Term Session & Memory

Bookings often take place over hours, days, or even a week.

-   **Database Persistence:** All conversation context, extracted details, and current states are stored in a dedicated database.
    
-   **Session Resurrection:** If a client returns after several days, the backend retrieves the active session, injecting the last known state into the Agent's prompt so the conversation continues seamlessly.
    
-   **Sender Awareness:** The system identifies whether an incoming message is from a **Client** (requesting a booking) or a **Worker** (updating availability/preferences) and routes the logic accordingly.
    

## 4) The Booking Lifecycle

### Step 1: Interaction Routing

The system identifies the sender type.

-   **Client:** The Agent checks for an active booking. If none exists, it initiates a new one.
    
-   **Worker:** The Agent queries the worker for updates or provides status reports on upcoming bookings.
    

### Step 2: Information Gathering (NLU)

The Agent interacts with the Client naturally. As details are provided, the Agent calls `update_booking_data` tools.

-   **Required Fields:** Age, Ethnicity, Type (Incall/Outcall), Date, Time, Duration, Location.
    
-   **Logic:** The backend tracks what is missing and instructs the Agent on what to ask next.
    

### Step 3: Conflict Handling & The 15-Minute Rule

When a time is suggested:

1.  The Agent calls a `check_availability` tool.
    
2.  The Backend queries the database for existing bookings.
    
3.  **Rule:** The backend ensures a mandatory **15-minute gap** between the end of one booking and the start of another.
    
4.  The Backend returns a simple "Success" or "Conflict" to the Agent.
    

### Step 4: Summary & Affirmative Confirmation

Once all data is collected and validated by the backend:

-   The Agent presents a clear summary to the Client.
    
-   The system enters an `AWAITING_CONFIRMATION` state.
    
-   The booking is only saved for Admin review once the Client provides a clear, affirmative "Yes."
    

### Step 5: Admin Review & Status Transitions

The booking moves through structured states:

-   **Pending:** Waiting for Admin to check details and receipts.
    
-   **Confirmed:** Admin approves; Agent notifies Client and Worker.
    
-   **Completed:** The session ends, and the flow resets for future interactions.
    
-   **Cancelled:** Admin or Client stops the process; context is archived.
    

## 5) Receipt Handling

-   Clients can upload images (proof of payment).
    
-   The backend associates these images with the specific Booking ID.
    
-   Admins can view these images directly in the dashboard to verify deposits (mandatory for Outcalls).
    

## 6) Admin Controls & Oversight

The Admin Dashboard provides:

-   **Live Monitoring:** View active sessions between Agent, Client, and Worker.
    
-   **Manual Override:** Ability to "Pause" the Agent to take over a conversation manually.
    
-   **Schedule View:** A visual representation of Worker availability including the 15-minute buffers.
    
-   **Notification Center:** Alerts for new receipts or bookings awaiting confirmation.
    

## 7) Technical Requirements for Success

-   **Relational Database:** To track complex relationships between the four entities.
    
-   **State Tracking:** A rigid field in the DB to define exactly where the conversation stands (e.g., `need_location`, `need_receipt`).
    
-   **Webhook Integration:** For real-time messaging across days or weeks.

---

## 8) Bug-Fix Expectations for AI Coding Agents (Post-Phase 6)

This section defines what future agents should optimize for when fixing bugs in this project.

### A) Current System Reality

-   Backend deterministic orchestration, Twilio channels, lifecycle, reliability hardening, JWT auth/RBAC, admin panel, worker portal, and realtime sync are already implemented.
-   The project is now in stabilization and launch-governance mode, not feature-discovery mode.
-   Any bug fix must preserve the backend state machine as source of truth.

### B) Priority Order for Bug Fixes

1.  **Booking correctness and safety** (state transitions, slot conflicts, review/decision flow)
2.  **Authorization correctness** (role checks + section `403` enforcement)
3.  **Message reliability** (dedup, out-of-order handling, retry/dead-letter, reminders)
4.  **Admin/worker UX resilience** (dashboard fail-soft behavior, realtime refresh stability)

### C) Non-Negotiable Behavior During Fixes

-   Do not bypass backend guards with prompt-only or frontend-only logic.
-   Keep Alysha persona and short 1-2 line response style intact.
-   Keep strict field order intact: `datetime -> age(18+) -> ethnicity -> duration -> name(optional)`.
-   Preserve cross-channel identity by `clients.phone_e164`.
-   Maintain worker section toggle behavior: hidden in UI and blocked in backend API when disabled.

### D) Known High-Risk Bug Classes

-   Dashboard/API partial failure should not blank the whole admin screen.
-   Availability checks must fail gracefully on malformed datetime inputs.
-   Realtime permission updates must propagate without requiring re-login.
-   Any direct call to disabled worker sections must return `403`.

### E) Required Verification After Every Bug Fix

-   Backend:
    - `ruff check .`
    - `mypy app`
    - `pytest`
    - `python -m pytest tests/test_phase6_track4_realtime.py -q`
-   Frontend:
    - `npm run build`
-   Runtime smoke:
    - admin dashboard loads with metrics/recent activity
    - worker section toggle immediately changes visibility/access
    - booking availability and confirmation flow remains deterministic

### F) Documentation Update Rule

-   If runtime behavior changes, update all relevant docs in the same patch:
    - `AGENTS.md`
    - `IMPLEMENTAION_PLAN.md`
    - `docs/API_ENDPOINTS.md`
    - `docs/WORKFLOWS.md`
    - this file (`AI Booking Assistant_ Features and Flow.md`)
