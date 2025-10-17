#include <iostream>
#include <string>
#include <vector>
#include <fstream>
#include <chrono>
#include <thread>

// VLC header file
#include <vlc/vlc.h>

// A structure to hold information for one subtitle entry
struct SubtitleItem {
    long long startTimeMs;
    long long endTimeMs;
};

// A helper function to convert SRT time format "HH:MM:SS,ms" to milliseconds
long long timeToMs(const std::string& timeStr) {
    try {
        long long h = std::stoll(timeStr.substr(0, 2));
        long long m = std::stoll(timeStr.substr(3, 2));
        long long s = std::stoll(timeStr.substr(6, 2));
        long long ms = std::stoll(timeStr.substr(9, 3));
        return h * 3600000 + m * 60000 + s * 1000 + ms;
    } catch (const std::exception& e) {
        std::cerr << "Error parsing time: " << timeStr << std::endl;
        return 0;
    }
}

// A simple function to parse an SRT file and extract timings
std::vector<SubtitleItem> parseSrt(const std::string& filename) {
    std::vector<SubtitleItem> subtitles;
    std::ifstream file(filename);

    if (!file.is_open()) {
        std::cerr << "Error: Could not open subtitle file: " << filename << std::endl;
        return subtitles;
    }

    std::string line;
    while (std::getline(file, line)) {
        if (line.find("-->") != std::string::npos) {
            SubtitleItem item;
            std::string startTimeStr = line.substr(0, 12);
            std::string endTimeStr = line.substr(17, 12);
            item.startTimeMs = timeToMs(startTimeStr);
            item.endTimeMs = timeToMs(endTimeStr);
            subtitles.push_back(item);
        }
    }

    std::cout << "Successfully parsed " << subtitles.size() << " subtitle entries." << std::endl;
    return subtitles;
}


int main() {
    // --- 1. Get User Input ---
    std::string videoPath, subtitlePath;
    int userRepeatCount;

    std::cout << "--- Foreign Language Video Player ---" << std::endl;
    std::cout << "Enter path to video file: ";
    std::getline(std::cin, videoPath);

    std::cout << "Enter path to subtitle file (.srt): ";
    std::getline(std::cin, subtitlePath);

    std::cout << "Enter repeat count (0 for no repeat): ";
    std::cin >> userRepeatCount;

    // --- 2. Parse Subtitles ---
    std::vector<SubtitleItem> subtitles = parseSrt(subtitlePath);
    if (subtitles.empty()) {
        return 1;
    }

    // --- 3. Initialize VLC ---
    libvlc_instance_t *vlc_inst;
    libvlc_media_player_t *media_player;
    libvlc_media_t *media;

    vlc_inst = libvlc_new(0, NULL);
    if (!vlc_inst) {
        std::cerr << "Error: Could not create VLC instance." << std::endl;
        return 1;
    }

    media = libvlc_media_new_path(vlc_inst, videoPath.c_str());
    if (!media) {
        std::cerr << "Error: Could not open video file." << std::endl;
        libvlc_release(vlc_inst);
        return 1;
    }

    // --- MODIFIED SECTION ---
    // The modern way to add a subtitle file is to add it as an option
    // to the media itself before creating the player.
    // We construct the option string: ":sub-file=/path/to/subtitle.srt"
    std::string sub_option = ":sub-file=" + subtitlePath;
    libvlc_media_add_option(media, sub_option.c_str());
    // --- END MODIFIED SECTION ---

    media_player = libvlc_media_player_new_from_media(media);
    libvlc_media_release(media);

    // --- 4. Start Playback and The Main Loop ---
    libvlc_media_player_play(media_player);

    std::cout << "\nPlayback started. The video window may appear separately." << std::endl;
    std::cout << "Press Ctrl+C in this terminal to quit." << std::endl;

    int currentSubtitleIndex = 0;
    int currentRepeat = 0;

    while (libvlc_media_player_is_playing(media_player) && currentSubtitleIndex < subtitles.size()) {
        const auto& currentSub = subtitles[currentSubtitleIndex];
        libvlc_time_t currentTime = libvlc_media_player_get_time(media_player);

        if (currentTime > currentSub.endTimeMs) {
            if (userRepeatCount > 0 && currentRepeat < userRepeatCount) {
                std::cout << "Repeating subtitle #" << (currentSubtitleIndex + 1)
                          << " (Repeat " << (currentRepeat + 1) << "/" << userRepeatCount << ")" << std::endl;

                libvlc_media_player_set_time(media_player, currentSub.startTimeMs);
                currentRepeat++;
            } else {
                currentSubtitleIndex++;
                currentRepeat = 0;
                if (currentSubtitleIndex < subtitles.size()) {
                     std::cout << "Moving to subtitle #" << (currentSubtitleIndex + 1) << std::endl;
                }
            }
        }

        std::this_thread::sleep_for(std::chrono::milliseconds(50));
    }

    std::cout << "\nPlayback finished or stopped. Cleaning up..." << std::endl;

    // --- 5. Cleanup ---
    libvlc_media_player_stop(media_player);
    libvlc_media_player_release(media_player);
    libvlc_release(vlc_inst);

    return 0;
}