import type { Messages } from "./types";

export const en: Messages = {
  app: {
    name: "EVA",
    tagline: "Always by your side…",
    aiBadge: "AI simulation",
  },
  onboarding: {
    title: "Hi, I'm EVA.",
    body: "Tell me your name; I'll learn the rest as we talk.",
    nameLabel: "What should I call you?",
    namePlaceholder: "Your name",
    disclosure:
      "EVA and the characters you talk to are AI simulations, not real people. In an emergency call your local emergency number.",
    ageConfirm: "I am 18 or older.",
    disclosureConfirm: "I have read and understood that EVA is an AI.",
    passkeyHint:
      "No password: you sign in with your fingerprint, face or screen lock, just like unlocking your phone or computer.",
    createAccount: "Create account with a passkey",
    haveAccount: "I already have an account",
    signIn: "Sign in with a passkey",
    backToSignUp: "Create a new account",
    signInTitle: "Welcome back.",
    signInBody: "Sign in with the passkey saved on this device.",
    errors: {
      unsupported:
        "This browser does not support passkeys. Try a recent Chrome, Safari, Edge or Firefox.",
      cancelled: "Cancelled or timed out. Please try again.",
      failed: "Verification failed. Please try again.",
      network: "Could not reach the server. Check your connection.",
    },
  },
  home: {
    greeting: "Hello",
    howAreYou: "How are you feeling today?",
    readyToTalk: "EVA is ready to talk.",
    moodTitle: "Your mood",
    moodSubtitle: "EVA will learn to read your mood as you talk.",
    actions: {
      chat: "Chat",
      voice: "Voice call",
      video: "Video",
      memories: "Memories",
      legacy: "Legacy",
    },
    evaCardDefault: "How are you today? 💙 If there's anything on your mind, I'm here.",
    evaCardFooter: "You matter",
    dailyMessage: "Message of the day",
    studioTitle: "Character Studio",
    studioSubtitle: "Sherlock, a historical figure or your own character.",
    comingSoon: "Soon",
  },
  nav: {
    home: "Home",
    insights: "Insights",
    explore: "Explore",
    profile: "Profile",
  },
  chat: {
    online: "online",
    typing: "typing…",
    placeholder: "Message EVA…",
    send: "Send",
    empty: "Say something, EVA is listening.",
    errorRetryable: "Connection hiccup, try again.",
    errorFatal: "Something went wrong.",
    interrupted: "(interrupted)",
    newConversation: "New chat",
  },
  comingSoon: {
    title: "Coming soon",
    body: "This part isn't ready yet. You can chat with EVA in the meantime.",
    back: "Back to home",
  },
  quotes: [
    "Small steps lead to big dreams.",
    "The only thing you can do today is live today well.",
    "Rest is part of the road too.",
    "Treat yourself the way you'd treat a friend.",
    "Not everything is fine, but you're on your way.",
  ],
};
