# Future Vision + Agency Approaches for Desktop AI

> Brainstorm document - saved for future exploration

---

## Novel Vision + Agency Methods for Desktop AI

### **1. Hardware-Level Approaches**

**HDMI Capture Card Loop**
- Route display output through capture card back to same machine
- Get raw pixels at hardware level, undetectable by software
- Zero permission issues, works with any app including DRM content
- Add USB input device that synthesizes HID events

**Actual Webcam Pointed at Screens**
- Literally a camera watching the monitors like a human would
- Could use depth camera (LiDAR) to understand physical layout
- Train vision model on "what a human sees" not "what a screenshot shows"
- Handles glare, ambient light, screen angles - real-world robustness

**Dedicated "AI Display"**
- Plug in a small secondary display that's actually a capture device
- Mirror primary display to it
- AI sees through its own "eye"

---

### **2. Virtual Machine / Hypervisor Level**

**Run macOS in VM, Control from Host**
- Full framebuffer access at hypervisor level
- Input injection is trivial (virtual HID)
- Complete isolation - AI can't affect host
- Snapshot/restore for safe experimentation
- Parallels/VMware/UTM all support this

**Docker + X11/Wayland Forwarding (Linux)**
- Run Linux GUI apps in containers
- Capture the virtual display
- Perfect for web apps via browser

---

### **3. Protocol/Network Level**

**Internal VNC/RDP Server-Client**
- Run VNC server on localhost
- Connect as client programmatically
- Screen updates come as protocol events (already diffed!)
- Input injection is native to protocol
- Works across network for distributed agents

**Reverse-Engineer Universal Control**
- Apple's cross-device protocol already streams screens
- Treat local Mac as if it were a remote iPad
- Leverage Apple's own optimized streaming

---

### **4. GPU/Rendering Pipeline Hooks**

**Metal/OpenGL Frame Interception**
- Hook into GPU submit calls
- See frames before they hit display
- Zero-copy access to rendered content
- Like what OBS/game capture does

**Virtual Display Driver**
- Create kernel extension that's a "display"
- All apps render to it thinking it's real
- Direct access to composited output
- CGVirtualDisplay API exists for this

**WindowServer Injection**
- Hook into macOS compositor
- See individual window textures before compositing
- Know exact window bounds, z-order, transparency

---

### **5. Semantic/Structured Approaches**

**Electron DevTools Protocol**
- Slack, Discord, VSCode are all Electron
- Connect via Chrome DevTools Protocol
- Get full DOM, execute JavaScript
- No vision needed - structured access

**Register as Assistive Technology**
- Beyond just using AX APIs
- Become a first-class assistive device
- Get push notifications of UI changes
- VoiceOver-level integration

**XPC Service Discovery**
- Many apps expose XPC services
- Direct programmatic control without UI
- Calendar, Mail, Messages all have this
- Combine with vision for apps that don't

---

### **6. AI-Native Approaches**

**Predictive State Model**
- Don't capture every frame
- Predict screen state from: last state + actions taken
- Only capture to verify predictions
- Massive bandwidth reduction

**Self-Supervised UI Learning**
- Agent records its own sessions
- Learns: "when I click here, this happens"
- Builds internal model of UI causality
- Eventually needs less vision, more prediction

**Multi-Agent Swarm**
- Multiple specialized agents
- One for OCR, one for UI detection, one for planning
- Parallel perception pipelines
- Consensus on what's on screen

**Continuous Embedding Space**
- Encode every frame to embedding
- Detect changes via embedding distance
- Semantic change detection, not pixel diff
- "Something important changed" vs "animation frame"

---

### **7. Hybrid Biological Approaches**

**Eye Tracking Hardware + Screen Recording**
- Track where human looks during demos
- Learn attention patterns for UI navigation
- "A human would look at the search box first"

**Audio Channel Fusion**
- macOS Sonoma has system audio capture
- Notifications make sounds
- Combine visual + audio for state understanding
- "I heard a ding, message probably arrived"

**Temporal Modeling**
- Don't just see current frame
- Maintain rolling buffer of last N seconds
- Understand animations, loading states, transitions
- "This spinner means loading, wait for it"

---

### **8. The Nuclear Option**

**SIP-Disabled Full System Hook**
- Disable System Integrity Protection
- dtrace everything, hook anything
- Direct memory read of any process
- Complete omniscience
- Obviously not for production

---

## Most Promising Combination

**VNC localhost + Electron CDP + Accessibility hybrid**

```
┌─────────────────────────────────────────────────────┐
│                   Agent Brain                        │
├─────────────────────────────────────────────────────┤
│ Perception Layer (parallel, redundant)              │
│  ├─ VNC Client (continuous frames, diffed)          │
│  ├─ ScreenCaptureKit (high-res on-demand)          │
│  ├─ CDP for Electron apps (structured DOM)          │
│  ├─ Accessibility APIs (semantic tree)             │
│  └─ Audio capture (event sounds)                   │
├─────────────────────────────────────────────────────┤
│ State Fusion (combine all inputs)                   │
│  ├─ Reconcile VNC pixels with AX tree              │
│  ├─ Override pixels with CDP DOM for Electron      │
│  └─ Predict missing data from action history       │
├─────────────────────────────────────────────────────┤
│ Action Layer (multiple paths)                       │
│  ├─ CGEvent (mouse/keyboard synthesis)             │
│  ├─ Accessibility actions (AXPress, AXSetValue)    │
│  ├─ CDP commands (click, type for Electron)        │
│  ├─ AppleScript (app-specific automation)          │
│  └─ XPC services (when available)                  │
└─────────────────────────────────────────────────────┘
```

The key insight: **use the right tool for each app type** rather than one universal approach:
- Electron apps via CDP
- Native apps via Accessibility  
- Games/DRM via hardware capture

---

## Status

**Parked** - This exploration is for another day. Current agent-screen and agent-gui provide basic functionality.
