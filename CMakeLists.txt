cmake_minimum_required(VERSION 3.16)

# Default to a Release build with g++ when the caller doesn't specify
# otherwise. This dev environment only has g++, cmake and Ninja installed.
if(NOT CMAKE_BUILD_TYPE)
    set(CMAKE_BUILD_TYPE Release CACHE STRING "Build type" FORCE)
endif()
if(NOT CMAKE_CXX_COMPILER AND NOT DEFINED ENV{CXX})
    set(CMAKE_CXX_COMPILER g++)
endif()

project(matching_engine_challenge CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)

# Performance flags for release builds. The server builds with GCC on Linux;
# the MSVC branch only exists so Windows participants can build locally.
if(MSVC)
    set(CMAKE_CXX_FLAGS_RELEASE "/O2 /DNDEBUG")
else()
    set(CMAKE_CXX_FLAGS_RELEASE "-O2 -march=native -DNDEBUG")
endif()

# Participants may add extra source files in src/ (flat, no sub-directories)
file(GLOB PARTICIPANT_SOURCES src/*.cpp src/*.cc)

add_library(matching_engine ${PARTICIPANT_SOURCES})
target_include_directories(matching_engine PUBLIC include)

# Correctness tests
add_executable(test_correctness test/test_correctness.cpp)
target_link_libraries(test_correctness matching_engine)

# Benchmark
add_executable(benchmark bench/benchmark.cpp bench/order_generator.cpp)
target_link_libraries(benchmark matching_engine)
