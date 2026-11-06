package com.resumeanalyser.job.feed;

/** A job feed could not be read right now (as opposed to "no such board"). */
public class JobFeedException extends RuntimeException {

    public JobFeedException(String message, Throwable cause) {
        super(message, cause);
    }
}
