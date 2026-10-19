#======local agent====#
import re
import subprocess
import webbrowser

import speech_recognition as sr

COMMANDS = {
    "open notepad": ("app", "notepad"),
    "start notepad": ("app", "notepad"),
    "নোটপ্যাড খোলো": ("app", "notepad"),
    "নোটপ্যাড চালু করো": ("app", "notepad"),

    "open calculator": ("app", "calc"),
    "ক্যালকুলেটর খোলো": ("app", "calc"),
    "ক্যালকুলেটর চালু করো": ("app", "calc"),

    "open chrome": ("site", "https://www.google.com/"),
    "ক্রোম খোলো": ("site", "https://www.google.com/"),

    "open youtube": ("site", "https://www.youtube.com/"),
    "ইউটিউব খোলো": ("site", "https://www.youtube.com/"),

    "open google": ("site", "https://www.google.com/"),
    "গুগল খোলো": ("site", "https://www.google.com/"),

    "open gmail": ("site", "https://mail.google.com/"),
    "জিমেইল খোলো": ("site", "https://mail.google.com/"),

    #================================
      # Microsoft Word
    "ms word": ("app", "winword"),
    "microsoft word": ("app", "winword"),
    "open word": ("app", "winword"),
    "open ms word": ("app", "winword"),
    "এমএস ওয়ার্ড": ("app", "winword"),
    "ওয়ার্ড খোলো": ("app", "winword"),

    # Microsoft Excel
    "open excel": ("app", "excel"),
    "open ms excel": ("app", "excel"),
    "ms excel": ("app", "excel"),
    "open xl": ("app", "excel"),
    "open x l": ("app", "excel"),
    "ওপেন এক্সেল": ("app", "excel"),
    "এক্সেল খোলো": ("app", "excel"),
    "ওপেন এক্সএল": ("app", "excel"),

    # Close Notepad
    "close notepad": ("close_app", "notepad"),
    "ক্লোজ নোটপ্যাড": ("close_app", "notepad"),
    "নোটপ্যাড বন্ধ করো": ("close_app", "notepad"),
    #================================
    "stop listening": ("stop", ""),
    "ভয়েস বন্ধ করো": ("stop", ""),
    "শোনা বন্ধ করো": ("stop", ""),
}


def normalize(text):
    text = text.lower().strip()
    text = re.sub(r"[.!?,;:'\"।]+", "", text)
    return re.sub(r"\s+", " ", text)


def execute(command):
    # Exact matching only. Unknown commands never run.
    action = COMMANDS.get(normalize(command))

    if action is None:
        print("Unknown command. No action taken.")
        return False

    kind, value = action

    if kind == "stop":
        print("Voice mode stopped.")
        return True

    if kind == "site":
        webbrowser.open(value)
        print("Website opened.")
        return False

    if kind == "app":
        try:
            subprocess.Popen([value + ".exe"], shell=False)
            print("Application opened.")
        except OSError as error:
            print("Could not open application:", error)

    return False


def voice_mode():
    recognizer = sr.Recognizer()
    recognizer.pause_threshold = 0.7

    try:
        microphone = sr.Microphone()
    except Exception as error:
        print("Microphone error:", error)
        return

    print("Online voice mode: Bengali + English")
    print("Internet required. Audio is sent to online recognition.")
    print("Say 'stop listening' to exit.")

    with microphone as source:
        print("Adjusting microphone...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    while True:
        try:
            with microphone as source:
                print("\nListening...")
                audio = recognizer.listen(
                    source,
                    timeout=6,
                    phrase_time_limit=6
                )

            # Try both languages on the same audio.
            matches = []

            for language in ("bn-BD", "en-US"):
                try:
                    text = recognizer.recognize_google(
                        audio,
                        language=language
                    )
                    print(f"Heard [{language}]: {text}")

                    action = COMMANDS.get(normalize(text))
                    if action is not None:
                        matches.append(action)

                except sr.UnknownValueError:
                    pass

            # Never guess when the two language results disagree.
            unique_matches = set(matches)

            if len(unique_matches) == 1:
                action = next(iter(unique_matches))
                # Reconstruct only the already-allowlisted action.
                if action[0] == "stop":
                    print("Voice mode stopped.")
                    return
                if action[0] == "site":
                    webbrowser.open(action[1])
                    print("Website opened.")
                elif action[0] == "app":
                    try:
                        subprocess.Popen(
                            [action[1] + ".exe"],
                            shell=False
                        )
                        print("Application opened.")
                    except OSError as error:
                        print("Could not open application:", error)

            elif len(unique_matches) > 1:
                print("Ambiguous result. No action taken.")
            else:
                print("Command not matched exactly. No action taken.")

        except sr.WaitTimeoutError:
            print("No speech detected. Try again.")
        except sr.RequestError as error:
            print("Online recognition error:", error)
            print("Check your internet connection.")
            return
        except KeyboardInterrupt:
            print("\nVoice mode stopped.")
            return


def main():
    print("=" * 55)
    print("MH2 PC Assistant — ONLINE VOICE")
    print("No Firebase or database.")
    print("Type /voice, /help, or /quit.")
    print("=" * 55)

    while True:
        try:
            text = input("MH2> ").strip()
        except (EOFError, KeyboardInterrupt):
            break

        if text.lower() == "/quit":
            break
        elif text.lower() == "/help":
            print("Say/type: Open Notepad, Open Calculator,")
            print("Open Chrome, Open YouTube, Open Google,")
            print("Open Gmail, or their listed Bengali equivalents.")
        elif text.lower() == "/voice":
            voice_mode()
        elif text:
            execute(text)

    print("Goodbye!")


if __name__ == "__main__":
    main()
