import weave

weave.init("sfs-ai-hackathon")

from controller import run_ascent


def main():
    run_ascent(target_altitude_m=20000.0)


if __name__ == "__main__":
    main()
