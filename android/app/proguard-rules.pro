# Media3 and OkHttp ship their own consumer rules; nothing extra is needed.

# NewPipeExtractor (YouTube search and audio streams): it reads YouTube's own pages and runs a little JavaScript (Rhino) to
# unscramble the stream addresses. Its parts are found by name and by reflection, so they must not be renamed or removed.
-keep class org.schabi.newpipe.extractor.** { *; }
-keep class org.mozilla.javascript.** { *; }
-keep class org.mozilla.classfile.ClassFileWriter
-keep class com.grack.nanojson.** { *; }
-keep class org.jsoup.** { *; }
-dontwarn java.beans.**
-dontwarn javax.script.**
-dontwarn jdk.dynalink.**
-dontwarn org.mozilla.javascript.tools.**
-dontwarn org.mozilla.javascript.engine.**
-dontwarn com.google.protobuf.**
-dontwarn javax.annotation.**
