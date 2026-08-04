from agents.orchestrator import CreatorOS

def main():

    creator = CreatorOS()

    source = input(
        "Enter YouTube URL or MP4 path:\n> "
    )

    creator.run(source)


if __name__ == "__main__":
    main()