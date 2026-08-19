from pathlib import Path


OUTPUT = Path(__file__).resolve().parent.parent / "assets" / "hero.svg"


def generate_hero():
    svg = """<svg
    xmlns="http://www.w3.org/2000/svg"
    width="1000"
    height="360"
    viewBox="0 0 1000 360"
    role="img"
    aria-labelledby="title desc"
>
    <title id="title">Anthony Fieldings III — AI Automation and Full-Stack Engineer</title>
    <desc id="desc">
        GitHub profile banner for Anthony Fieldings III, also known as PublicStringTre.
    </desc>

    <defs>
        <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stop-color="#08080d"/>
            <stop offset="55%" stop-color="#0d0914"/>
            <stop offset="100%" stop-color="#160923"/>
        </linearGradient>

        <linearGradient id="purpleLine" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#7c3aed"/>
            <stop offset="50%" stop-color="#c084fc"/>
            <stop offset="100%" stop-color="#7c3aed"/>
        </linearGradient>

        <filter id="purpleGlow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="blur"/>
            <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
            </feMerge>
        </filter>
    </defs>

    <!-- Main background -->
    <rect
        x="1"
        y="1"
        width="998"
        height="358"
        rx="18"
        fill="url(#background)"
        stroke="#342044"
        stroke-width="2"
    />

    <!-- Top terminal bar -->
    <rect
        x="1"
        y="1"
        width="998"
        height="48"
        rx="18"
        fill="#111118"
    />

    <rect x="1" y="31" width="998" height="18" fill="#111118"/>

    <!-- Terminal buttons -->
    <circle cx="28" cy="25" r="6" fill="#ff5f57"/>
    <circle cx="49" cy="25" r="6" fill="#febc2e"/>
    <circle cx="70" cy="25" r="6" fill="#28c840"/>

    <text
        x="500"
        y="30"
        text-anchor="middle"
        fill="#777786"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="13"
    >
        publicstringtre@github: ~/profile
    </text>

    <!-- Command -->
    <text
        x="48"
        y="92"
        fill="#c084fc"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="17"
        font-weight="600"
    >
        tre@github
    </text>

    <text
        x="147"
        y="92"
        fill="#777786"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="17"
    >
        :
    </text>

    <text
        x="158"
        y="92"
        fill="#a78bfa"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="17"
    >
        ~
    </text>

    <text
        x="176"
        y="92"
        fill="#f8fafc"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="17"
    >
        $ whoami
    </text>

    <!-- Name -->
    <text
        x="48"
        y="145"
        fill="#ffffff"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="38"
        font-weight="700"
        letter-spacing="1"
    >
        ANTHONY FIELDINGS III
    </text>

    <!-- Role -->
    <text
        x="49"
        y="182"
        fill="#c084fc"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="20"
        font-weight="600"
        letter-spacing="2"
    >
        AI AUTOMATION + FULL-STACK ENGINEER
    </text>

    <!-- Accent line -->
    <rect
        x="49"
        y="204"
        width="900"
        height="2"
        rx="1"
        fill="url(#purpleLine)"
        filter="url(#purpleGlow)"
    />

    <!-- Status block -->
    <text
        x="49"
        y="247"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="14"
    >
        STATUS
    </text>

    <circle cx="119" cy="242" r="5" fill="#22c55e"/>

    <text
        x="132"
        y="247"
        fill="#e4e4e7"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="14"
    >
        BUILDING
    </text>

    <text
        x="274"
        y="247"
        fill="#71717a"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="14"
    >
        FOCUS
    </text>

    <text
        x="331"
        y="247"
        fill="#e4e4e7"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="14"
    >
        AI • AUTOMATION • VOICE • RAG
    </text>

    <!-- Bottom tagline -->
    <text
        x="49"
        y="300"
        fill="#a1a1aa"
        font-family="SFMono-Regular, Consolas, Liberation Mono, monospace"
        font-size="16"
    >
        &gt; building intelligent systems that turn AI into actual software
    </text>

    <!-- Cursor -->
    <rect
        x="49"
        y="320"
        width="10"
        height="3"
        rx="1"
        fill="#c084fc"
    />
</svg>
"""

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(svg, encoding="utf-8")

    print(f"Generated: {OUTPUT}")


if __name__ == "__main__":
    generate_hero()